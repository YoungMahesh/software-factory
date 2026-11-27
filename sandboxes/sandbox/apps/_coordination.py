"""Factory state transitions; executed only by the serialized state authority in Modal."""

from datetime import datetime, timezone

from ._models import (
    DEFAULT_APP_BASE_PORT, RESUMABLE_STEPS, FactoryAppRecord, LaunchRequestRecord, LaunchStatus, LaunchStatusResponse,
    PrimeSandboxRecord, prime_compatibility_key_for_app, utc_now_iso,
)


def _stale(timestamp: str | None, seconds: float) -> bool:
    try:
        parsed = datetime.fromisoformat(timestamp or "")
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() >= seconds


class StateTransitions:
    """Owns claims, fencing, reservations and failure disposition behind the store interface.

    Storage primitives are private collaborators on FactoryStateStore. Its reentrant
    lock protects local callers; deployed callers all enter the single Modal authority.
    No cloud provisioning or sandbox calls may execute while a transition holds the lock.
    """

    def assert_request_active(self, app_id: str, request_id: str) -> None:
        app = self.get_app(app_id, reload=False)
        if app is None or app.latest_request_id != request_id:
            raise RuntimeError(f"Launch Request '{request_id}' was superseded or deleted.")

    def claim_launch_execution(self, request_id: str) -> bool:
        with self._lock:
            launch = self.get_launch(request_id)
            if launch is None:
                raise KeyError(request_id)
            self.assert_request_active(launch.app_id, request_id)
            if launch.status in ("ready", "failed"):
                return False
            # The launch worker has a hard 600-second lifetime. A dead worker's
            # request can be redelivered after that lifetime plus a safety margin.
            if launch.execution_started_at and not _stale(launch.execution_started_at, 660):
                return False
            self.update_launch(request_id, execution_started_at=utc_now_iso())
            return True

    def record_launch_stage(self, request_id: str, status: LaunchStatus, label: str, **details) -> LaunchRequestRecord:
        def advance(current):
            if status != "failed":
                self.assert_request_active(current.app_id, request_id)
            return current.with_stage(status, label, **details)
        return self.modify_launch(request_id, advance)

    def complete_launch_request(self, app_id: str, request_id: str, updates: dict,
                                handoff_url: str, handoff_expires_at: str) -> LaunchStatusResponse:
        with self._lock:
            current = self.get_app(app_id)
            self.assert_request_active(app_id, request_id)
            launch = self.get_launch(request_id, reload=False)
            if launch is None:
                raise RuntimeError("Launch Request was deleted before completion.")
            now = utc_now_iso()
            app = current.model_copy(update={**updates, "status": "ready", "failed_step": None,
                                             "last_error": None, "updated_at": now})
            launch = launch.with_stage(
                "ready", "Ready — opening T3 Code", log_lines=[f"Ready: {app.chat_url}"],
                handoff_url=handoff_url, handoff_expires_at=handoff_expires_at,
            ).model_copy(update={"updated_at": now})
            self._write_model_file(self._app_path(app_id), app)
            self._write_model_file(self._launch_path(request_id), launch)
            self._commit_volume()
            return LaunchStatusResponse(request=launch, app=app)

    def append_launch_logs(self, request_id: str, lines: list[str]) -> LaunchRequestRecord:
        return self.modify_launch(request_id, lambda cur: cur.with_appended_logs(lines))

    def claim_prime(self, app_id: str, request_id: str, *, stale_secs: float = 420) -> PrimeSandboxRecord:
        with self._lock:
            self._reload_volume()
            self.assert_request_active(app_id, request_id)
            app = self.get_app(app_id, reload=False)
            key = app.prime_key or prime_compatibility_key_for_app(app)
            current = self.get_prime(key, reload=False)
            if current is not None and current.status == "ready":
                return current
            if current is not None and current.status == "provisioning":
                owner = self.get_launch(current.owner_request_id, reload=False) if current.owner_request_id else None
                owner_app = self.get_app(owner.app_id, reload=False) if owner else None
                alive = (
                    owner is not None and owner.status not in ("ready", "failed")
                    and owner_app is not None and owner_app.latest_request_id == current.owner_request_id
                    and not _stale(current.updated_at, stale_secs)
                )
                if alive:
                    return current
            return self.save_prime(PrimeSandboxRecord(
                prime_key=key, profile=app.profile, vm=app.vm, mobile_app=app.mobile_app,
                status="provisioning", owner_request_id=request_id,
            ))

    def bind_prime_sandbox(self, prime_key: str, request_id: str, sandbox_id: str,
                           sandbox_name: str | None, t3_url: str) -> bool:
        with self._lock:
            current = self.get_prime(prime_key)
            if current is None or current.status != "provisioning" or current.owner_request_id != request_id:
                return False
            self.update_launch(request_id, created_sandbox_id=sandbox_id)
            self.save_prime(current.model_copy(update={
                "sandbox_id": sandbox_id, "sandbox_name": sandbox_name, "t3_url": t3_url,
            }))
            return True

    def mark_prime_ready(self, prime_key: str, *, request_id: str, sandbox_id: str,
                         sandbox_name: str | None, t3_url: str, environment_id: str) -> PrimeSandboxRecord:
        with self._lock:
            current = self.get_prime(prime_key)
            launch = self.get_launch(request_id, reload=False)
            if launch is None:
                raise RuntimeError("Prime Sandbox owner was deleted.")
            self.assert_request_active(launch.app_id, request_id)
            if (current is None or current.status != "provisioning"
                    or current.owner_request_id != request_id or current.sandbox_id != sandbox_id):
                raise RuntimeError("Prime Sandbox provisioning claim was lost.")
            ready = current.model_copy(update={
                "status": "ready", "owner_request_id": None, "sandbox_id": sandbox_id,
                "sandbox_name": sandbox_name, "t3_url": t3_url, "environment_id": environment_id,
                "updated_at": utc_now_iso(),
            })
            self._write_model_file(self._launch_path(request_id), launch.model_copy(update={
                "published_sandbox_id": sandbox_id, "updated_at": utc_now_iso(),
            }))
            self._write_model_file(self._prime_path(prime_key), ready)
            self._commit_volume()
            return ready

    def mark_prime_stopped(self, sandbox_id: str | None) -> None:
        if not sandbox_id:
            return
        with self._lock:
            for current in self.list_primes():
                if current.sandbox_id == sandbox_id and current.status in ("ready", "provisioning"):
                    self.save_prime(current.model_copy(update={"status": "stopped", "owner_request_id": None}))

    def delete_apps_for_sandbox(self, sandbox_id: str | None, *, keep_provisioning: bool = False) -> int:
        """Deletes Factory Apps (and launches) bound to a terminated sandbox_id and marks Prime stopped."""
        if not sandbox_id:
            return 0
        with self._lock:
            self.mark_prime_stopped(sandbox_id)
            deleted = 0
            for app in self.list_apps():
                if app.sandbox_id != sandbox_id:
                    continue
                if keep_provisioning and app.status == "provisioning":
                    continue
                if self.delete_app(app.app_id):
                    deleted += 1
            return deleted

    def release_prime_claim(self, prime_key: str, request_id: str) -> None:
        with self._lock:
            current = self.get_prime(prime_key)
            if current and current.status == "provisioning" and current.owner_request_id == request_id:
                self.save_prime(current.model_copy(update={"status": "failed", "owner_request_id": None}))

    def reserve_dev_port(self, prime_key: str, sandbox_id: str, *, request_id: str) -> int:
        with self._lock:
            launch = self.get_launch(request_id)
            if launch is None:
                raise RuntimeError("Launch Request was deleted before port reservation.")
            self.assert_request_active(launch.app_id, request_id)
            app = self.get_app(launch.app_id, reload=False)
            if app.sandbox_id == sandbox_id and app.dev_port is not None:
                return app.dev_port
            current = self.get_prime(prime_key, reload=False)
            used = [a.dev_port for a in self.list_apps() if a.sandbox_id == sandbox_id and a.dev_port is not None]
            next_unused = max(used, default=DEFAULT_APP_BASE_PORT - 1) + 1
            if current and current.sandbox_id == sandbox_id:
                if current.status == "provisioning" and current.owner_request_id != request_id:
                    raise RuntimeError("Prime Sandbox provisioning claim was lost.")
                if current.status not in ("provisioning", "ready"):
                    raise RuntimeError("Prime Sandbox is no longer active.")
                port = max(current.next_port, next_unused)
                self._write_model_file(self._prime_path(prime_key), current.model_copy(update={
                    "next_port": port + 1, "updated_at": utc_now_iso(),
                }))
            else:
                # Preserved recovery containers can outlive their compatibility-key
                # record. Persist the reservation before another caller can inspect it.
                if app.sandbox_id != sandbox_id:
                    raise RuntimeError("Prime Sandbox provisioning claim was lost.")
                port = next_unused
            self._write_model_file(self._app_path(app.app_id), app.model_copy(update={
                "sandbox_id": sandbox_id, "dev_port": port, "updated_at": utc_now_iso(),
            }))
            self._commit_volume()
            return port

    def fail_launch_request(self, app: FactoryAppRecord, launch: LaunchRequestRecord, *,
                            current_step: str, sandbox_id: str | None, t3_url: str | None,
                            prime_key: str, error: str) -> tuple[LaunchStatusResponse, bool]:
        with self._lock:
            self._reload_volume()
            current_app = self.get_app(app.app_id, reload=False)
            active = current_app is not None and current_app.latest_request_id == launch.request_id
            preserve = active and current_step in RESUMABLE_STEPS and bool(sandbox_id and t3_url)
            prime = self.get_prime(prime_key, reload=False)
            owns = prime is not None and prime.status == "provisioning" and prime.owner_request_id == launch.request_id
            # Published ready containers are shared, even if no sibling has written
            # its app attachment yet. They must never be terminated by app failure.
            stored_launch = self.get_launch(launch.request_id, reload=False)
            created = stored_launch is not None and stored_launch.created_sandbox_id == sandbox_id
            published = stored_launch is not None and stored_launch.published_sandbox_id == sandbox_id
            shared = published or (prime is not None and prime.status == "ready" and prime.sandbox_id == sandbox_id)
            shared = shared or any(a.app_id != app.app_id and a.sandbox_id == sandbox_id for a in self.list_apps())
            terminate = bool(sandbox_id and (created or (owns and prime.sandbox_id == sandbox_id))
                             and not preserve and not shared)
            updated_app = self.update_app_if_current_request(
                app.app_id, launch.request_id, status="failed", failed_step=current_step,
                sandbox_id=sandbox_id if preserve else None, last_error=error,
            )
            try:
                updated_launch = self.record_launch_stage(
                    launch.request_id, "failed", "Launch failed", error=error,
                    failed_step=current_step, log_lines=[f"Error ({current_step}): {error}"],
                )
            except KeyError:
                updated_launch = launch.with_stage("failed", "Launch failed", error=error, failed_step=current_step)
            self.release_prime_claim(prime_key, launch.request_id)
            return LaunchStatusResponse(request=updated_launch, app=updated_app or current_app), terminate
