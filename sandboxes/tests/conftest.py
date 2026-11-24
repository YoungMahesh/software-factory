"""Keep unit-test sandbox launches out of the operator's Codex profile pool."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_codex_profile_assignment():
    with patch("sandbox.launcher.prepare_profile", return_value=None) as prepare:
        yield prepare
