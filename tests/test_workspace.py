from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from metawispr.api import create_app
from metawispr.config import Settings


class WorkspaceTests(unittest.TestCase):
    def test_static_workspace_preserves_api_and_missing_path_responses(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ui = root / 'ui'
            ui.mkdir()
            (ui / 'index.html').write_text('<!doctype html><title>Workspace fixture</title>', encoding='utf-8')
            (ui / 'asset.js').write_text('/* explicit static test fixture */', encoding='utf-8')
            with TestClient(create_app(Settings(data_dir=root / 'data', ui_dir=ui))) as client:
                self.assertIn('Workspace fixture', client.get('/?meeting=example').text)
                self.assertEqual(client.get('/asset.js').status_code, 200)
                self.assertEqual(client.get('/api/meetings').json(), {'meetings': []})
                self.assertEqual(client.get('/api/unknown').status_code, 404)
                self.assertEqual(client.get('/missing.js').status_code, 404)
                self.assertEqual(client.get('/%2e%2e/pyproject.toml').status_code, 404)

    def test_unbuilt_workspace_has_actionable_setup_without_breaking_api(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with TestClient(create_app(Settings(data_dir=root / 'data', ui_dir=root / 'missing'))) as client:
                response = client.get('/')
                self.assertEqual(response.status_code, 503)
                self.assertIn('npm run build', response.json()['detail'])
                self.assertEqual(client.get('/api/meetings').status_code, 200)
