"""Subsystem tests for Modal Sandbox Runner Web UI authentication."""

import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sandbox.web import app


class TestWebAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unconfigured_credentials_raises_500(self):
        # When WEB_UI_USERNAME / WEB_UI_PASSWORD are not set, permissive access is gone; returns 500
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 500)
            self.assertIn("Server authentication misconfigured", response.json()["detail"])

    def test_auth_enforced_when_credentials_set(self):
        env = {
            "WEB_UI_USERNAME": "superadmin",
            "WEB_UI_PASSWORD": "secretpassword",
        }
        with patch.dict(os.environ, env, clear=True):
            # Unauthorized request (missing header)
            res_unauth = self.client.get("/")
            self.assertEqual(res_unauth.status_code, 401)
            self.assertIn("WWW-Authenticate", res_unauth.headers)
            self.assertIn("Authentication required", res_unauth.json()["detail"])

            # Wrong scheme
            res_scheme = self.client.get("/", headers={"Authorization": "Bearer some-token"})
            self.assertEqual(res_scheme.status_code, 401)
            self.assertIn("Invalid authentication scheme", res_scheme.json()["detail"])

            # Wrong password
            bad_auth = base64.b64encode(b"superadmin:wrongpass").decode()
            res_bad = self.client.get("/", headers={"Authorization": f"Basic {bad_auth}"})
            self.assertEqual(res_bad.status_code, 401)
            self.assertIn("Incorrect authentication credentials", res_bad.json()["detail"])

            # Correct Basic Auth
            good_auth = base64.b64encode(b"superadmin:secretpassword").decode()
            res_good = self.client.get("/", headers={"Authorization": f"Basic {good_auth}"})
            self.assertEqual(res_good.status_code, 200)

            # Favicon remains public
            res_fav = self.client.get("/favicon.ico")
            self.assertEqual(res_fav.status_code, 204)

    def test_bearer_token_not_accepted_for_web_ui(self):
        env = {
            "WEB_UI_USERNAME": "superadmin",
            "WEB_UI_PASSWORD": "secretpassword",
        }
        with patch.dict(os.environ, env, clear=True):
            # Bearer token is rejected on Web UI
            res_bearer = self.client.get("/", headers={"Authorization": "Bearer token-xyz-123"})
            self.assertEqual(res_bearer.status_code, 401)

            # Basic Auth using wrong password is rejected if it doesn't match WEB_UI_PASSWORD
            basic_tok = base64.b64encode(b"superadmin:wrong-password").decode()
            res_basic = self.client.get("/", headers={"Authorization": f"Basic {basic_tok}"})
            self.assertEqual(res_basic.status_code, 401)


if __name__ == "__main__":
    unittest.main()
