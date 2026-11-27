"""State authority transport: only named, serializable domain operations cross this seam."""

from typing import Callable

from ._store import FactoryStateStore

# No callback-based mutations cross the worker seam. The authority owns transitions.
_OPERATIONS = frozenset({
    "get_app", "list_apps", "delete_app", "delete_apps_for_sandbox", "update_app_if_current_request",
    "get_launch", "create_app_and_launch", "record_launch_stage", "append_launch_logs",
    "get_prime", "list_primes", "claim_prime", "bind_prime_sandbox", "mark_prime_ready",
    "mark_prime_stopped", "release_prime_claim", "reserve_dev_port", "fail_launch_request",
    "get_repo_catalog", "save_repo_catalog", "get_scratchpad_catalog", "save_scratchpad_catalog",
    "record_scratchpad_commit", "cache_scratchpad_body", "delete_scratchpad_note_cache",
    "claim_launch_execution", "assert_request_active", "complete_launch_request",
})


def dispatch_state_operation(store: FactoryStateStore, operation: str, args: tuple, kwargs: dict):
    """Executes one whole transition inside the single authority, never in a worker."""
    if operation not in _OPERATIONS:
        raise ValueError(f"Unsupported factory state operation: {operation}")
    # Re-read the last durable commit after a cold start; reload failure must fail
    # closed rather than letting an old filesystem snapshot overwrite current state.
    with store._lock:
        store._reload_volume()
        return getattr(store, operation)(*args, **kwargs)


class FactoryStateClient:
    """Worker adapter for the same state interface, with no local cache or Volume mount.

    Modal serializes arguments/results, including the domain records. Keeping the
    transport adapter here makes it possible to verify the identical dispatch seam
    against a state authority in a separate OS process without cloud resources.
    """

    def __init__(self, send: Callable):
        self._send = send

    def __getattr__(self, operation: str):
        if operation not in _OPERATIONS:
            raise AttributeError(operation)
        return lambda *args, **kwargs: self._send(operation, args, kwargs)
