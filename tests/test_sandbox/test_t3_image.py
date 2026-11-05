"""Modal image and binary patching tests for T3 Code integration."""

import ast
import base64
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch


class TestT3CodeImage(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]

    def test_t3_patch_script_contains_driver_order_and_model_pruning(self):
        from shared.image import (
            T3_DRIVER_ORDER_PATCH_TARGET,
            T3_DRIVER_ORDER_PATCH_REPLACEMENT,
            T3_CURRENT_MODELS_PATCH_TARGET,
            T3_CURRENT_MODELS_PATCH_REPLACEMENT,
            T3_MODELS_MANIFEST_PATCH_TARGET,
            T3_MODELS_MANIFEST_PATCH_REPLACEMENT,
            T3_PATCH_SCRIPT,
        )

        t_order = base64.b64decode(T3_DRIVER_ORDER_PATCH_TARGET).decode("utf-8")
        r_order = base64.b64decode(T3_DRIVER_ORDER_PATCH_REPLACEMENT).decode("utf-8")
        self.assertIn('"opencode"', t_order)
        self.assertIn('"antigravity"', r_order)
        self.assertLess(t_order.find('"opencode"'), t_order.find('"antigravity"'))
        self.assertLess(r_order.find('"antigravity"'), r_order.find('"opencode"'))

        t_cur = base64.b64decode(T3_CURRENT_MODELS_PATCH_TARGET).decode("utf-8")
        r_cur = base64.b64decode(T3_CURRENT_MODELS_PATCH_REPLACEMENT).decode("utf-8")
        self.assertIn("gemini-3.8-flash-medium", t_cur)
        self.assertIn('"gemini-3.8-flash-high"/*', r_cur)

        self.assertIn(T3_DRIVER_ORDER_PATCH_TARGET, T3_PATCH_SCRIPT)
        self.assertIn(T3_CURRENT_MODELS_PATCH_TARGET, T3_PATCH_SCRIPT)
        self.assertIn(T3_MODELS_MANIFEST_PATCH_TARGET, T3_PATCH_SCRIPT)

    def test_build_sandbox_image_stages_multiple_antigravity_accounts(self):
        from shared.image import (
            LOCAL_ANTIGRAVITY_SECRET,
            LOCAL_ANTIGRAVITY_SECRET_MGH,
            LOCAL_ANTIGRAVITY_SECRET_ANV,
            LOCAL_ANTIGRAVITY_ENV,
            REMOTE_ANTIGRAVITY_SECRET,
            REMOTE_ANTIGRAVITY_SECRET_MGH,
            REMOTE_ANTIGRAVITY_SECRET_ANV,
            REMOTE_ANTIGRAVITY_ENV,
        )

        self.assertTrue(str(LOCAL_ANTIGRAVITY_SECRET_MGH).endswith("antigravity-oauth-token-mgh.json"))
        self.assertTrue(str(LOCAL_ANTIGRAVITY_SECRET_ANV).endswith("antigravity-oauth-token-anv.json"))
        self.assertTrue(str(LOCAL_ANTIGRAVITY_ENV).endswith("antigravity.env"))
        self.assertEqual(REMOTE_ANTIGRAVITY_SECRET_MGH, "/root/secrets/antigravity-oauth-token-mgh.json")
        self.assertEqual(REMOTE_ANTIGRAVITY_SECRET_ANV, "/root/secrets/antigravity-oauth-token-anv.json")
        self.assertEqual(REMOTE_ANTIGRAVITY_ENV, "/root/secrets/antigravity.env")

    def test_build_sandbox_image_layers_t3(self):
        from shared.image import (
            build_sandbox_image,
            T3_TAR_URL,
            T3_PATCH_SCRIPT,
            T3_ANTIGRAVITY_URL,
            T3_ANTIGRAVITY_VERSION_DIR,
            T3_ANTIGRAVITY_MANAGED_DIR,
            T3_INSTALL_COMPLETE_JSON,
            T3_ACTIVE_JSON,
            LOCAL_OPENCODE_CONFIG,
            REMOTE_OPENCODE_CONFIG,
            LOCAL_OPENCODE_SECRET,
            REMOTE_OPENCODE_SECRET,
            LOCAL_ANTIGRAVITY_SECRET,
            LOCAL_ANTIGRAVITY_SECRET_MGH,
            LOCAL_ANTIGRAVITY_SECRET_ANV,
            LOCAL_ANTIGRAVITY_ENV,
            REMOTE_ANTIGRAVITY_SECRET,
            REMOTE_ANTIGRAVITY_SECRET_MGH,
            REMOTE_ANTIGRAVITY_SECRET_ANV,
            REMOTE_ANTIGRAVITY_ENV,
            LOCAL_T3_KEYBINDINGS,
            REMOTE_T3_KEYBINDINGS,
            LOCAL_T3_WRAPPER,
            REMOTE_T3_WRAPPER,
        )

        with patch("shared.image.base_image") as mock_base, patch(
            "shared.image.add_local_files_if_present"
        ) as mock_add_files:
            mock_img1 = MagicMock()
            mock_img2 = MagicMock()
            mock_img3 = MagicMock()
            mock_base.run_commands.return_value = mock_img1
            mock_add_files.side_effect = lambda img, *args, **kwargs: img
            mock_img1.run_commands.return_value = mock_img2
            mock_img2.env.return_value = mock_img3

            result = build_sandbox_image(t3=True)

            mock_base.run_commands.assert_called_once_with(
                "curl -fsSL https://opencode.ai/v2/install | bash"
            )
            mock_add_files.assert_has_calls(
                [
                    call(
                        mock_img1,
                        [
                            (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
                            (LOCAL_OPENCODE_SECRET, REMOTE_OPENCODE_SECRET),
                        ],
                    ),
                    call(
                        mock_img2,
                        [
                            (LOCAL_T3_KEYBINDINGS, REMOTE_T3_KEYBINDINGS),
                            (LOCAL_T3_WRAPPER, REMOTE_T3_WRAPPER),
                        ],
                    ),
                    call(
                        mock_img2,
                        [
                            (LOCAL_ANTIGRAVITY_SECRET, REMOTE_ANTIGRAVITY_SECRET),
                            (LOCAL_ANTIGRAVITY_SECRET_MGH, REMOTE_ANTIGRAVITY_SECRET_MGH),
                            (LOCAL_ANTIGRAVITY_SECRET_ANV, REMOTE_ANTIGRAVITY_SECRET_ANV),
                            (LOCAL_ANTIGRAVITY_ENV, REMOTE_ANTIGRAVITY_ENV),
                        ],
                    ),
                ]
            )
            mock_img1.run_commands.assert_called_once_with(
                "mkdir -p /opt/t3",
                f"curl -fsSL {T3_TAR_URL} | tar -xz -C /opt/t3 --strip-components=1",
                "ln -sf /opt/t3/t3 /usr/local/bin/t3",
                T3_PATCH_SCRIPT,
                f"mkdir -p {T3_ANTIGRAVITY_VERSION_DIR}",
                f"curl -fsSL {T3_ANTIGRAVITY_URL} -o /tmp/agy-acp.zip",
                f"unzip -q /tmp/agy-acp.zip -d {T3_ANTIGRAVITY_VERSION_DIR}",
                "rm -f /tmp/agy-acp.zip",
                (
                    f"chmod 0755 {T3_ANTIGRAVITY_VERSION_DIR}/agy_acp_server.par "
                    f"{T3_ANTIGRAVITY_VERSION_DIR}/localharness_external"
                ),
                f"echo '{T3_INSTALL_COMPLETE_JSON}' > {T3_ANTIGRAVITY_VERSION_DIR}/.install-complete.json",
                f"echo '{T3_ACTIVE_JSON}' > {T3_ANTIGRAVITY_MANAGED_DIR}/active.json",
            )
            mock_img2.env.assert_called_once_with(
                {"PATH": "/root/.opencode/bin:${PATH}"}
            )

    def test_t3_patch_script_validity_and_execution(self):
        from shared.image import T3_PATCH_SCRIPT

        self.assertTrue(T3_PATCH_SCRIPT.startswith("python3 -c '") and T3_PATCH_SCRIPT.endswith("'"))
        py_code = T3_PATCH_SCRIPT[len("python3 -c '") : -1]

        try:
            ast.parse(py_code)
        except SyntaxError as e:
            self.fail(f"T3_PATCH_SCRIPT contains invalid Python syntax: {e}")

        with tempfile.TemporaryDirectory() as tmpdir:
            test_bin = Path(tmpdir) / "t3"
            t = base64.b64decode(
                "ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpIHsKCXJldHVybiB7CgkJY29tbWFuZDogaW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAoJCWFyZ3M6IGlucHV0LnByb2ZpbGUucGxhdGZvcm0gPT09ICJsaW51eCIgPyBbIi0tdWlkPSJdIDogW10sCgkJY3dkOiBpbnB1dC5jd2QsCgkJZW52OiB7CgkJCS4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5wdXQucHJvZmlsZSwgaW5wdXQuYmFzZUVudiA/PyBwcm9jZXNzLmVudiwgaW5wdXQuYXV0aCA/PyBBTlRJR1JBVklUWV9QRVJTT05BTF9BVVRILCBpbnB1dC5ydW50aW1lVGVtcERpcmVjdG9yeSksCgkJCUFOVElHUkFWSVRZX0hBUk5FU1NfUEFUSDogaW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCgkJfSwKCQlleHRlbmRFbnY6IGZhbHNlCgl9Owp9"
            )
            r = base64.b64decode(
                "ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpewpyZXR1cm57CmNvbW1hbmQ6aW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAphcmdzOiBpbnB1dC5wcm9maWxlLnBsYXRmb3JtPT09ImxpbnV4Ij9bIi0tZW5mb3JjZV9rZXJuZWxfaXB2Nl9zdXBwb3J0PWZhbHNlIiwiLS11aWQ9Il06W10sCmN3ZDppbnB1dC5jd2QsCmVudjp7Ci4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5wdXQucHJvZmlsZSxpbnB1dC5iYXNlRW52Pz9wcm9jZXNzLmVudiwgaW5wdXQuYXV0aD8/QU5USUdSQVZJVFlfUEVSU09OQUxfQVVUSCwgaW5wdXQucnVudGltZVRlbXBEaXJlY3RvcnkpLApBTlRJR1JBVklUWV9IQVJORVNTX1BBVEg6aW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCn0sCmV4dGVuZEVudjpmYWxzZQp9Owp9"
            )
            self.assertEqual(len(t), 426)
            self.assertEqual(len(r), 426)
            self.assertEqual(len(t), len(r), "Patch must be length-preserving to prevent SEA corruption")

            initial_content = b"PREFIX_" + t + b"_SUFFIX"
            test_bin.write_bytes(initial_content)

            test_cmd = T3_PATCH_SCRIPT.replace("/opt/t3/t3", str(test_bin))
            res = subprocess.run(["bash", "-c", test_cmd], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Patch script failed: {res.stderr}")

            patched_content = test_bin.read_bytes()
            self.assertIn(b"--enforce_kernel_ipv6_support=false", patched_content)
            self.assertNotIn(t, patched_content)
            self.assertEqual(len(patched_content), len(initial_content), "Binary size must not change")

            # Verify idempotency on already-patched binary
            res_idempotent = subprocess.run(["bash", "-c", test_cmd], capture_output=True, text=True)
            self.assertEqual(res_idempotent.returncode, 0, f"Idempotent patch failed: {res_idempotent.stderr}")
            self.assertEqual(test_bin.read_bytes(), patched_content)

    def test_t3_ssh_remote_open_target_patch_exact_length(self):
        from shared.image import (
            T3_SSH_PATCH_TARGET,
            T3_SSH_PATCH_REPLACEMENT,
            T3_PATCH_SCRIPT,
        )

        t = base64.b64decode(T3_SSH_PATCH_TARGET)
        r = base64.b64decode(T3_SSH_PATCH_REPLACEMENT)
        self.assertEqual(len(t), 248)
        self.assertEqual(len(r), 248)
        self.assertEqual(len(t), len(r))
        self.assertIn("T3_SSH_HOST", r.decode("utf-8"))
        self.assertIn("SANDBOX_NAME", r.decode("utf-8"))
        self.assertIn("assert len(t2) == len(r2) == 248", T3_PATCH_SCRIPT)
