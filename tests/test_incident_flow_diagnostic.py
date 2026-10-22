import json
import unittest
from scripts.check_incident_flow import summarize_push


class IncidentFlowDiagnosticTests(unittest.TestCase):
    def test_acceptance_count_is_not_device_receipt_and_secrets_are_omitted(self):
        result = summarize_push(json.dumps({
            "version": 1, "status": "FINISHED", "attempts": 1,
            "results": {"secret-token-hash": {"status": "ACCEPTED", "code": "secret-key"}},
            "targets": ["secret-token"], "reason": "secret-url",
        }))
        self.assertEqual(result["device_counts"]["ACCEPTED"], 1)
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn("received", result)

    def test_missing_and_corrupt_records_do_not_mean_success(self):
        self.assertEqual(summarize_push(None)["status"], "NO_REDIS_RECORD")
        for raw in ["not-json", "[]", '{"version":1,"status":"private-secret"}',
                    '{"version":1,"status":"FINISHED","results":{"x":{"status":"secret"}}}']:
            self.assertEqual(summarize_push(raw), {"status": "INVALID_REDIS_RECORD"})

    def test_partial_device_results_remain_distinct(self):
        result = summarize_push(json.dumps({"version": 1, "status": "WAITING", "attempts": 2,
            "results": {"a": {"status": "ACCEPTED"}, "b": {"status": "RETRY"}}}))
        self.assertEqual(result["status"], "WAITING")
        self.assertEqual(result["device_counts"]["RETRY"], 1)


if __name__ == "__main__":
    unittest.main()
