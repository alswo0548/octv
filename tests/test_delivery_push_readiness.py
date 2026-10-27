"""Offline, secret-free tests for the additive preflight (not an FCM send test)."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_delivery_push_readiness import audit, _timestamp_state, _url_state


class DeliveryPushReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "backend").mkdir()
        (self.root / "frontend" / "mobile").mkdir(parents=True)
        (self.root / ".env").write_text("OCTV_REDIS_URL=redis://127.0.0.1:6379/0\n")
        (self.root / "backend" / ".env").write_text(
            "OCTV_REDIS_URL=redis://127.0.0.1:6379/0\n"
            "OCTV_FIREBASE_PROJECT_ID=example-project\n"
            "GOOGLE_APPLICATION_CREDENTIALS=C:\\private\\firebase.json\n"
            "OCTV_PUSH_ENABLED=0\nOCTV_PUSH_START_AT=\n")
        (self.root / "frontend" / "mobile" / ".env").write_text(
            "EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:8000\n"
            "OCTV_ANDROID_ALLOW_HTTP=0\nOCTV_ANDROID_PACKAGE=com.octv.mobile\n")
        (self.root / "frontend" / "mobile" / "google-services.json").write_text(json.dumps({
            "project_info": {"project_id": "example-project"},
            "client": [{"client_info": {"android_client_info": {"package_name": "com.octv.mobile"}}}],
        }))

    def test_http_disabled_detected_without_exposing_url_or_secrets(self):
        out = audit(self.root, platform="posix", process_env={})
        self.assertEqual(out["settings"]["mobile_api"], "HTTP_BLOCKED_BY_ANDROID_CONFIG")
        self.assertEqual(out["settings"]["firebase_credentials"], "CHECK_ON_WINDOWS")
        self.assertEqual(out["settings"]["firebase_android_client"], "CLIENT_CONFIG_MATCHED")
        self.assertIn("ANDROID_API_CONFIG_REQUIRED", out["local_blockers"])
        self.assertIn("TEST_RECIPIENT_AND_PUSH_ENABLE_APPROVAL", out["approval_gates"])
        text = json.dumps(out)
        self.assertNotIn("192.168.1.10", text)
        self.assertNotIn("example-project", text)
        self.assertNotIn("private", text)

    def test_http_local_fix_changes_result_without_editing_file(self):
        path = self.root / "frontend" / "mobile" / ".env"
        before = path.read_bytes()
        self.assertEqual(_url_state("http://192.168.1.10:8000", "1"),
                         "READY_FOR_CONNECTIVITY_TEST")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(_url_state("http://localhost:8000", "1"),
                         "ANDROID_LOOPBACK_NOT_PC")
        self.assertEqual(_url_state("https://app.example.invalid", "0"),
                         "READY_FOR_CONNECTIVITY_TEST")
        self.assertEqual(_url_state("http://192.168.1.10:8000/api", "1"),
                         "INVALID_URL")

    def test_start_requires_timezone(self):
        self.assertEqual(_timestamp_state(""), "NOT_CONFIGURED")
        self.assertEqual(_timestamp_state("2026-10-26T21:00:00"), "TIMEZONE_REQUIRED")
        self.assertEqual(_timestamp_state("not-a-date"), "INVALID")
        self.assertEqual(_timestamp_state("2026-01-01T09:00:00+09:00"), "VALID")


if __name__ == "__main__":
    unittest.main()
