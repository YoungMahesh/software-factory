"""Keep unit tests out of operator HTTP endpoints and Codex credential profiles."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def block_unmocked_http():
    # A local .env once made a missing-endpoint test provision a real sandbox.
    # Explicit HTTP mocks still override this guard inside individual tests.
    with patch("urllib.request.urlopen", side_effect=AssertionError(
        "Unit test attempted an unmocked HTTP request; inject a transport adapter."
    )):
        yield


@pytest.fixture(autouse=True)
def mock_codex_profile_assignment():
    with patch("sandbox.launcher.prepare_profile", return_value=None) as prepare:
        yield prepare
