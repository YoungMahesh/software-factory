"""Unit tests for the Modal Documentation Web App."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sandbox.docs import (
    APP_NAME,
    app,
    create_docs_app,
    docs_image,
    docs_web_app,
)


class TestDocsApp(unittest.TestCase):
    """Test suite for the static documentation FastAPI application."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.site_path = Path(self.temp_dir.name)

        # Create mock compiled site structure
        (self.site_path / "index.html").write_text("<h1>Modal Sandboxes Docs</h1>", encoding="utf-8")
        nested_dir = self.site_path / "getting-started"
        nested_dir.mkdir(parents=True, exist_ok=True)
        (nested_dir / "index.html").write_text("<h1>Getting Started</h1>", encoding="utf-8")
        (self.site_path / "404.html").write_text("<h1>Page Not Found</h1>", encoding="utf-8")

        self.app = create_docs_app(self.site_path)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_root_index_html(self):
        """Root GET request should serve the index.html page."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Modal Sandboxes Docs", response.text)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_nested_directory_route(self):
        """Directory route should resolve to the index.html within that folder."""
        response = self.client.get("/getting-started/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Getting Started", response.text)

    def test_not_found_status(self):
        """Request for non-existent path should return 404 status."""
        response = self.client.get("/non-existent-page")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_site_directory_graceful_handling(self):
        """App creation should handle missing directory gracefully without failing."""
        missing_path = Path("/nonexistent/directory/for/testing")
        empty_app = create_docs_app(missing_path)
        client = TestClient(empty_app)
        response = client.get("/")
        self.assertEqual(response.status_code, 404)

    def test_modal_app_invariants(self):
        """Modal application definition should have expected name and properties."""
        self.assertEqual(APP_NAME, "modal-sandboxes-docs")
        self.assertEqual(app.name, "modal-sandboxes-docs")
        self.assertIsNotNone(docs_image)

    def test_docs_web_app_factory(self):
        """Invoking docs_web_app via .local() should return a FastAPI instance."""
        with patch("sandbox.docs.create_docs_app", wraps=create_docs_app) as mock_create:
            fastapi_instance = docs_web_app.local()
            self.assertIsNotNone(fastapi_instance)
            mock_create.assert_called_once_with("/root/site")

    def test_mkdocs_emoji_extension_configured(self):
        """Verify mkdocs.yml configures pymdownx.emoji for Material and Octicons rendering."""
        mkdocs_path = Path(__file__).resolve().parent.parent / "mkdocs.yml"
        self.assertTrue(mkdocs_path.is_file(), "mkdocs.yml must exist at repo root")
        content = mkdocs_path.read_text(encoding="utf-8")
        self.assertIn("pymdownx.emoji:", content)
        self.assertIn("material.extensions.emoji.twemoji", content)
        self.assertIn("material.extensions.emoji.to_svg", content)
