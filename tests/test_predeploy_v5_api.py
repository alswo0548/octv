import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.demo_v5_media.router import router
from backend.app.dependencies import get_current_user

class V5ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
    def test_anonymous_cannot_read_preview_or_archive(self):
        for path in ['/api/demo/v5/preview/4','/api/demo/v5/archive-scope']:
            self.assertEqual(self.client.get(path).status_code,401)
    def test_agency_cannot_read_admin_previews(self):
        self.app.dependency_overrides[get_current_user] = lambda: {'role':'AGENCY_STAFF','is_active':True}
        for path in ['/api/demo/v5/preview/4','/api/demo/v5/archive-scope']:
            self.assertEqual(self.client.get(path).status_code,403)
    def test_archive_only_reads_and_limits_known_demo_identifiers(self):
        self.app.dependency_overrides[get_current_user] = lambda: {'role':'CONTROL_ADMIN','is_active':True}
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [{'id':5}]
        @contextmanager
        def connection(): yield conn
        with patch('backend.app.demo_v5_media.router.get_connection',connection):
            result = self.client.get('/api/demo/v5/archive-scope')
        self.assertEqual(result.json(),{'archived_ids':[5]})
        calls = conn.execute.call_args_list
        self.assertEqual(calls[0].args[0], 'SET TRANSACTION READ ONLY')
        self.assertEqual(calls[1].args[1], (['DEMO-N001','DEMO-N002','DEMO-N003'],))
        self.assertNotIn('DELETE', calls[1].args[0])
