"""CCTV 마지막 프레임 KST DB 시각이 API에서 정확한 UTC가 되는지 확인한다."""

from datetime import datetime, timedelta, timezone
import unittest

from backend.app.cctvs.schemas import CctvResponse


class CctvLastFrameTimezoneTests(unittest.TestCase):
    def setUp(self):
        self.cctv = {
            "id": 3,
            "external_cctv_id": "E910012",
            "name": "시연 CCTV",
            "provider": "UTIC",
            "latitude": 37.0,
            "longitude": 127.0,
            "is_monitored": True,
            "connection_status": "CONNECTED",
        }

    def test_kst_naive_db_timestamp_becomes_utc(self):
        response = CctvResponse(**self.cctv, last_frame_at=datetime(2026, 10, 22, 9, 3))
        self.assertEqual(response.last_frame_at, datetime(2026, 10, 22, 0, 3, tzinfo=timezone.utc))
        self.assertEqual(response.model_dump(mode="json")["last_frame_at"], "2026-10-22T00:03:00Z")

    def test_timezone_aware_values_preserve_instant(self):
        expected = datetime(2026, 10, 22, 0, 3, tzinfo=timezone.utc)
        kst = datetime(2026, 10, 22, 9, 3, tzinfo=timezone(timedelta(hours=9)))
        for original in (kst, expected):
            with self.subTest(original=original):
                self.assertEqual(CctvResponse(**self.cctv, last_frame_at=original).last_frame_at, expected)

    def test_missing_timestamp_remains_null(self):
        self.assertIsNone(CctvResponse(**self.cctv, last_frame_at=None).last_frame_at)


if __name__ == "__main__":
    unittest.main()
