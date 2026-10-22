"""ITS 링크의 대량 응답 및 구조 변형에 대한 오프라인 회귀 검사. API/DB/Redis 호출 없음."""
import unittest
from unittest.mock import patch
from backend.app.integrations import auto_match_providers as providers


class ItsTrafficLinkResponseTests(unittest.TestCase):
    def test_its_list_payload_variants(self):
        for body in (
            {"items": {"item": [{"linkId": "A12"}]}},
            {"items": [{"linkId": "A12"}]},
            {"items": {"item": {"linkId": "A12"}}},
            {"items": []},
        ):
            with self.subTest(body=body):
                rows = providers._traffic_records({
                    "response": {"header": {"resultCode": "0"}, "body": body}
                })
                self.assertEqual(rows, [] if body["items"] == [] else [{"linkId": "A12"}])

    def test_top_level_items_and_wrapped_data(self):
        for payload in (
            {"items": {"item": [{"linkId": "123"}]}},
            {"data": {"item": [{"linkId": "123"}]}},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(providers._traffic_records(payload), [{"linkId": "123"}])

    def test_provider_error_not_counted_as_empty(self):
        self.assertIsNone(providers._traffic_records({
            "response": {"header": {"resultCode": "1"},
                         "body": {"items": []}}
        }))

    def test_traffic_lookup_uses_12_second_timeout_and_does_not_verify_direction(self):
        cctv = {"id":3,"latitude":37.2,"longitude":127.1,"name":"Test"}
        payload = {"response":{"header":{"resultCode":"0"},
                   "body":{"items":[{"linkId":"991", "roadName":"Test"}]}}}
        with patch.object(providers, "_safe_get_json", return_value=payload) as mocked:
            result = providers.find_traffic_mapping(cctv, "NOT_REAL_KEY")
            self.assertEqual(mocked.call_args.kwargs["timeout_seconds"], 12.0)
            self.assertEqual(result["status"], "DIRECTION_UNVERIFIED")
            self.assertFalse(result["candidates"][0]["geometry_verified"])

    def test_water_station_keeps_default_timeout(self):
        # 관측소 조회의 기존 제한시간은 변경하지 않습니다.
        self.assertEqual(providers._safe_get_json.__kwdefaults__["timeout_seconds"],4.0)


if __name__ == "__main__":
    unittest.main()
