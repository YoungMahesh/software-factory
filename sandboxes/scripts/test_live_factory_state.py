"""Verify Factory State Authority with isolated Modal workers and ephemeral storage.

Run explicitly: python sandboxes/scripts/test_live_factory_state.py.
Does not deploy the control plane or create sandboxes. All cloud resources are ephemeral.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "sandboxes"))
import modal
from sandbox.config import resolve_factory_credentials
from sandbox.profiles import get_client_for_profile


def main():
    resolve_factory_credentials(mutate_environ=True)
    client = get_client_for_profile()
    image = (modal.Image.debian_slim(python_version="3.12")
        .pip_install("modal==1.6.4", "pydantic>=2", "fastapi", "python-dotenv", "qrcode", "httpx")
        .add_local_python_source("sandbox", "shared")
        .add_local_dir(root / "sandboxes" / "shared", "/root/shared", ignore=["skills/**", "**/__pycache__/**"]))
    with modal.Volume.ephemeral(client=client) as volume:
        app = modal.App("factory-state-authority-verification")

        @app.function(image=image, volumes={"/state": volume}, max_containers=1, timeout=60, serialized=True)
        def authority(operation, args, kwargs):
            from sandbox.apps._store import FactoryStateStore
            from sandbox.apps._state_rpc import dispatch_state_operation
            return dispatch_state_operation(FactoryStateStore(root_dir="/state", volume=volume), operation, args, kwargs)

        @app.function(image=image, max_containers=4, timeout=120, serialized=True)
        def worker(index):
            from sandbox.apps import CreateAppPayload, LaunchCoordinator
            from sandbox.apps._state_rpc import FactoryStateClient
            store = FactoryStateClient(authority.remote)
            app, launch = LaunchCoordinator(store=store, env={}).create_and_dispatch(CreateAppPayload(prompt="Verification app"))
            claimed = store.claim_launch_execution(launch.request_id)
            prime = store.claim_prime(app.app_id, launch.request_id)
            return app, launch, claimed, prime.owner_request_id

        with app.run(client=client):
            calls = [worker.spawn(i) for i in range(4)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                records = list(pool.map(lambda call: call.get(timeout=180), calls))
            from sandbox.apps._state_rpc import FactoryStateClient
            store = FactoryStateClient(authority.remote)
            assert len({record[0].slug for record in records}) == 4
            owners = {record[3] for record in records}
            assert len(owners) == 1
            owner = owners.pop()
            key = records[0][0].prime_key
            assert store.bind_prime_sandbox(key, owner, "sb-verification-only", "fixture", "https://fixture.test")
            store.mark_prime_ready(key, request_id=owner, sandbox_id="sb-verification-only", sandbox_name="fixture",
                                   t3_url="https://fixture.test", environment_id="env-verification")
            ports = [store.reserve_dev_port(key, "sb-verification-only", request_id=record[1].request_id) for record in records]
            assert sorted(ports) == list(range(3001, 3005))
            assert not store.claim_launch_execution(owner)
            print("PASS: four Modal workers, one provisioning owner, four unique workspaces and ports, duplicate delivery suppressed")
            print("No sandbox was provisioned. Test App and Volume are ephemeral and close with their contexts.")


if __name__ == "__main__":
    main()
