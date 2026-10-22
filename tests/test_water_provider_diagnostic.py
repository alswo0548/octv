"""수위 API 단발성 진단: 실제 API/DB/Redis 요청 없이 검사."""
import unittest
from unittest.mock import patch

from scripts import check_water_provider


class WaterProviderDiagnosticTests(unittest.TestCase):
    def station(self):
        return {"wlobscd": "1018683", "obsnm": "한강대교", "wrnwl": "3.1",
                "almwl": "4.5", "srswl": "6.0"}

    def test_941_stops_after_one_call_without_exposing_key(self):
        with patch.object(check_water_provider.diag, "request_once", return_value=(
            {"status": "HTTP_RESPONSE", "http_status": 200, "api_status": {"code": "941"}},
            {"code": "941", "message": None},
        )) as call:
            report = check_water_provider.check_water("SECRET", "1018683")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(report["provider_code"], "941")
        self.assertEqual(report["meaning"], "UNVERIFIED_BY_PROVIDER")
        self.assertNotIn("SECRET", str(report))

    def test_info_only_is_one_request(self):
        with patch.object(check_water_provider.diag, "request_once", return_value=(
            {"status": "HTTP_RESPONSE", "http_status": 200},
            {"content": [self.station()]},
        )) as call:
            report = check_water_provider.check_water("SECRET")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(report["station_count"], 1)

    def test_exact_station_reads_10m_and_thresholds(self):
        responses = [
            ({"status": "HTTP_RESPONSE"}, {"content": [self.station()]}),
            ({"status": "HTTP_RESPONSE"}, {"content": [
                {"wlobscd": "1018683", "ymdhm": "202610221340", "wl": "3.6"},
                {"wlobscd": "1018684", "ymdhm": "202610221350", "wl": "8.0"},
            ]}),
        ]
        with patch.object(check_water_provider.diag, "request_once", side_effect=responses) as call:
            report = check_water_provider.check_water("SECRET", "1018683")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(report["thresholds"]["status"], "VALID_OFFICIAL_STATION_DATA")
        self.assertEqual(report["water_level_m"], 3.6)
        self.assertEqual(report["latest_observed_at_kst"], "202610221340")
        self.assertNotIn("SECRET", str(report))

    def test_invalid_station_does_not_call_api(self):
        with patch.object(check_water_provider.diag, "request_once") as call:
            report = check_water_provider.check_water("KEY", "../../bad")
        self.assertEqual(report["status"], "INVALID_STATION_ID")
        call.assert_not_called()

    def test_stale_or_missing_station_measurement_not_assumed_safe(self):
        responses = [
            ({"status": "HTTP_RESPONSE"}, {"content": [self.station()]}),
            ({"status": "HTTP_RESPONSE"}, {"code": "941", "message": None}),
        ]
        with patch.object(check_water_provider.diag, "request_once", side_effect=responses):
            report = check_water_provider.check_water("KEY", "1018683")
        self.assertEqual(report["observation_status"], "API_ERROR_OR_SCHEMA_UNKNOWN")
        self.assertNotIn("water_level_m", report)


if __name__ == "__main__":
    unittest.main()
