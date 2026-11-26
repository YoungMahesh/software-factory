"""Verify the deployed state seam using independent client and authority processes."""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from multiprocessing.managers import BaseManager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sandbox.apps import CreateAppPayload, FactoryStateStore, LaunchCoordinator, prime_compatibility_key
from sandbox.apps._state_rpc import FactoryStateClient, dispatch_state_operation


class _Authority:
    def __init__(self, root):
        self.store = FactoryStateStore(root_dir=root)

    def send(self, operation, args, kwargs):
        return dispatch_state_operation(self.store, operation, args, kwargs)

    def age_claim(self, key):
        current = self.store.get_prime(key)
        self.store.save_prime(current.model_copy(update={"updated_at": "2000-01-01T00:00:00+00:00"}))
        # save_prime refreshes updated_at; simulate a committed old record directly.
        current = self.store.get_prime(key).model_copy(update={"updated_at": "2000-01-01T00:00:00+00:00"})
        self.store._write_model_file(self.store._prime_path(key), current)


class _Manager(BaseManager):
    pass


_Manager.register("Authority", _Authority)


@pytest.fixture
def authority(tmp_path):
    with _Manager(ctx=multiprocessing.get_context("spawn")) as manager:
        yield manager.Authority(str(tmp_path))


def _create_and_claim(authority, index):
    client = FactoryStateClient(authority.send)
    app, launch = LaunchCoordinator(store=client, env={}).create_and_dispatch(CreateAppPayload(prompt="Same app"))
    execution = client.claim_launch_execution(launch.request_id)
    prime = client.claim_prime(app.app_id, launch.request_id)
    return app, launch, execution, prime.owner_request_id


def _reserve(authority, request_id):
    return FactoryStateClient(authority.send).reserve_dev_port(
        prime_compatibility_key(None, False, False), "sb-shared", request_id=request_id,
    )


def test_independent_workers_share_one_owner_unique_slugs_and_ports(authority):
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as workers:
        records = list(workers.map(_create_and_claim, [authority] * 8, range(8)))
        owners = {owner for _, _, _, owner in records}
        assert len(owners) == 1
        assert len({app.slug for app, _, _, _ in records}) == 8
        assert all(executed for _, _, executed, _ in records)
        client = FactoryStateClient(authority.send)
        owner = owners.pop()
        key = prime_compatibility_key(None, False, False)
        assert client.bind_prime_sandbox(key, owner, "sb-shared", "prime", "https://t3.test")
        client.mark_prime_ready(key, request_id=owner, sandbox_id="sb-shared", sandbox_name="prime",
                                t3_url="https://t3.test", environment_id="env-1")
        request_ids = [launch.request_id for _, launch, _, _ in records]
        ports = list(workers.map(_reserve, [authority] * 8, request_ids))
        assert sorted(ports) == list(range(3001, 3009))
        # Reservations and execution delivery are idempotent across fresh clients.
        assert list(workers.map(_reserve, [authority] * 8, request_ids)) == ports
        assert not client.claim_launch_execution(owner)
        assert {a.dev_port for a in client.list_apps()} == set(ports)


def test_takeover_fences_late_owner_and_release_cannot_clobber_successor(authority):
    first, first_request, _, _ = _create_and_claim(authority, 0)
    second, second_request, _, _ = _create_and_claim(authority, 1)
    client = FactoryStateClient(authority.send)
    key = first.prime_key
    authority.age_claim(key)
    taken = client.claim_prime(second.app_id, second_request.request_id)
    assert taken.owner_request_id == second_request.request_id
    assert not client.bind_prime_sandbox(key, first_request.request_id, "sb-old", "old", "https://old.test")
    client.release_prime_claim(key, first_request.request_id)
    assert client.get_prime(key).owner_request_id == second_request.request_id
    assert client.bind_prime_sandbox(key, second_request.request_id, "sb-new", "new", "https://new.test")
    with pytest.raises(RuntimeError, match="claim was lost"):
        client.mark_prime_ready(key, request_id=first_request.request_id, sandbox_id="sb-old",
                                sandbox_name="old", t3_url="https://old.test", environment_id="env-old")
    client.mark_prime_ready(key, request_id=second_request.request_id, sandbox_id="sb-new",
                            sandbox_name="new", t3_url="https://new.test", environment_id="env-new")
    assert client.get_prime(key).sandbox_id == "sb-new"


def test_published_prime_survives_owner_failure_before_sibling_attachment(authority):
    app, launch, _, _ = _create_and_claim(authority, 0)
    client = FactoryStateClient(authority.send)
    client.bind_prime_sandbox(app.prime_key, launch.request_id, "sb-shared", "prime", "https://t3.test")
    client.mark_prime_ready(app.prime_key, request_id=launch.request_id, sandbox_id="sb-shared",
                            sandbox_name="prime", t3_url="https://t3.test", environment_id="env-1")
    client.delete_app(app.app_id)
    result, terminate = client.fail_launch_request(
        app, launch, current_step="starting_thread", sandbox_id="sb-shared", t3_url="https://t3.test",
        prime_key=app.prime_key, error="deleted",
    )
    assert not terminate
    assert result.app is None
    assert client.get_prime(app.prime_key).status == "ready"


def test_private_provisioning_failure_releases_only_its_own_container(authority):
    app, launch, _, _ = _create_and_claim(authority, 0)
    client = FactoryStateClient(authority.send)
    client.bind_prime_sandbox(app.prime_key, launch.request_id, "sb-private", "prime", "https://t3.test")
    _, terminate = client.fail_launch_request(
        app, launch, current_step="launching_sandbox", sandbox_id="sb-private", t3_url="https://t3.test",
        prime_key=app.prime_key, error="failed",
    )
    assert terminate
    assert client.get_prime(app.prime_key).status == "failed"


def test_state_authority_fails_closed_on_reload_and_rejects_callback_operations(tmp_path):
    volume = MagicMock()
    volume.reload.side_effect = RuntimeError("reload failed")
    store = FactoryStateStore(root_dir=tmp_path, volume=volume)
    with pytest.raises(RuntimeError, match="reload failed"):
        dispatch_state_operation(store, "list_apps", (), {})
    with pytest.raises(ValueError, match="Unsupported"):
        dispatch_state_operation(store, "modify_prime", (), {})
    with pytest.raises(AttributeError):
        FactoryStateClient(lambda *args: None).modify_prime
    assert not list(Path(tmp_path).rglob("*.json"))


def test_full_launch_crosses_remote_state_seam_and_duplicate_delivery_is_inert(authority):
    from .test_prime_sandbox import _MultiAppFakeSandbox
    from sandbox.core import LaunchResponse

    sb = _MultiAppFakeSandbox()
    launch_fn = MagicMock(return_value=(sb, LaunchResponse(
        sandbox_id=sb.object_id, app_name="prime", sandbox_name="prime", t3_url="https://t3.test",
    )))
    coordinator = LaunchCoordinator(
        store=FactoryStateClient(authority.send), env={}, launch_fn=launch_fn,
        sandbox_from_id_fn=lambda *args, **kwargs: sb,
    )
    _, request = coordinator.create_and_dispatch(CreateAppPayload(prompt="Test remote state"))
    response = coordinator.execute_launch_request(request.request_id)
    assert response.request.status == "ready"
    assert response.app.dev_port == 3001
    repeated = coordinator.execute_launch_request(request.request_id)
    assert repeated.request.status == "ready"
    assert launch_fn.call_count == 1


def test_corrupt_prime_record_cannot_be_replaced_by_a_new_owner(tmp_path):
    store = FactoryStateStore(root_dir=tmp_path)
    app, launch = LaunchCoordinator(store=store, env={}).create_and_dispatch(CreateAppPayload(prompt="State corruption"))
    path = tmp_path / "primes" / f"{app.prime_key}.json"
    path.write_text("{corrupt")
    with pytest.raises(RuntimeError, match="Failed parsing factory state"):
        store.claim_prime(app.app_id, launch.request_id)
    assert path.read_text() == "{corrupt"


def test_authority_restart_retains_claims_and_reservations(tmp_path):
    with _Manager(ctx=multiprocessing.get_context("spawn")) as manager:
        first = manager.Authority(str(tmp_path))
        app, launch, _, _ = _create_and_claim(first, 0)
        client = FactoryStateClient(first.send)
        client.bind_prime_sandbox(app.prime_key, launch.request_id, "sb-shared", "prime", "https://t3.test")
        assert client.reserve_dev_port(app.prime_key, "sb-shared", request_id=launch.request_id) == 3001
    with _Manager(ctx=multiprocessing.get_context("spawn")) as manager:
        second = manager.Authority(str(tmp_path))
        client = FactoryStateClient(second.send)
        assert not client.claim_launch_execution(launch.request_id)
        assert client.get_prime(app.prime_key).owner_request_id == launch.request_id
        assert client.reserve_dev_port(app.prime_key, "sb-shared", request_id=launch.request_id) == 3001
        assert client.get_prime(app.prime_key).next_port == 3002


def test_superseded_launch_cannot_publish_progress_or_completion(authority):
    from sandbox.apps import LaunchRequestRecord

    app, launch, _, _ = _create_and_claim(authority, 0)
    client = FactoryStateClient(authority.send)
    client.create_app_and_launch(app.model_copy(update={"latest_request_id": "req-replacement"}),
                                 LaunchRequestRecord(request_id="req-replacement", app_id=app.app_id))
    with pytest.raises(RuntimeError, match="superseded"):
        client.record_launch_stage(launch.request_id, "starting_thread", "Late progress")
    with pytest.raises(RuntimeError, match="superseded"):
        client.complete_launch_request(app.app_id, launch.request_id, {}, "https://old.test", "2999-01-01T00:00:00Z")
    assert client.get_app(app.app_id).latest_request_id == "req-replacement"
    assert client.get_launch("req-replacement").status == "queued"


def test_late_private_owner_can_clean_up_its_container_after_takeover(authority):
    app, launch, _, _ = _create_and_claim(authority, 0)
    client = FactoryStateClient(authority.send)
    assert client.bind_prime_sandbox(app.prime_key, launch.request_id, "sb-old", "old", "https://old.test")
    successor, successor_request, _, _ = _create_and_claim(authority, 1)
    authority.age_claim(app.prime_key)
    client.claim_prime(successor.app_id, successor_request.request_id)
    _, terminate = client.fail_launch_request(
        app, launch, current_step="launching_sandbox", sandbox_id="sb-old", t3_url="https://old.test",
        prime_key=app.prime_key, error="lost ownership",
    )
    assert terminate
    assert client.get_prime(app.prime_key).owner_request_id == successor_request.request_id


def test_published_container_stays_protected_after_prime_record_replacement(authority):
    app, launch, _, _ = _create_and_claim(authority, 0)
    client = FactoryStateClient(authority.send)
    client.bind_prime_sandbox(app.prime_key, launch.request_id, "sb-old", "old", "https://old.test")
    client.mark_prime_ready(app.prime_key, request_id=launch.request_id, sandbox_id="sb-old",
                            sandbox_name="old", t3_url="https://old.test", environment_id="env-old")
    client.mark_prime_stopped("sb-old")
    successor, successor_request, _, _ = _create_and_claim(authority, 1)
    # Supersede the owner app to force non-preserving failure disposition.
    from sandbox.apps import LaunchRequestRecord
    client.create_app_and_launch(app.model_copy(update={"latest_request_id": "req-new"}),
                                 LaunchRequestRecord(request_id="req-new", app_id=app.app_id))
    _, terminate = client.fail_launch_request(
        app, launch, current_step="starting_thread", sandbox_id="sb-old", t3_url="https://old.test",
        prime_key=app.prime_key, error="superseded",
    )
    assert not terminate
    assert client.get_prime(app.prime_key).owner_request_id == successor_request.request_id
