"""Execute the dashboard observation scenarios with the real JavaScript module."""

from pathlib import Path
import shutil
import subprocess


def test_launch_observation_lifetime():
    node = shutil.which("node")
    assert node, "Node.js is required to verify the Sandbox Web Dashboard"
    suite = Path(__file__).parent / "dashboard" / "launch-observer.cjs"
    result = subprocess.run([node, "--test", str(suite)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_dashboard_observer_asset_is_served_under_dashboard_auth(monkeypatch):
    from fastapi.testclient import TestClient
    from sandbox.web import app

    monkeypatch.setenv("WEB_UI_USERNAME", "testadmin")
    monkeypatch.setenv("WEB_UI_PASSWORD", "testpassword")
    client = TestClient(app)
    assert client.get("/static/launch-observer.js").status_code == 401
    response = client.get("/static/launch-observer.js", auth=("testadmin", "testpassword"))
    assert response.status_code == 200
    assert "function createLaunchObserver" in response.text
    assert "text/javascript" in response.headers["content-type"]
    assert '/static/launch-observer.js' in client.get("/", auth=("testadmin", "testpassword")).text
