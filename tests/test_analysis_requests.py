import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.app import analysis_requests


class AnalysisRequestTests(unittest.TestCase):
    def setUp(self):
        self.incident_id = 123
        self.incident = {
            "id": self.incident_id,
            "status": "DETECTED",
            "risk_score": None,
            "hazard_type": "flood",
        }

    def test_request_analysis_returns_not_queued_when_analysis_not_needed(self):
        with patch.object(
            analysis_requests,
            "get_analysis_input",
            return_value=None,
        ):
            result = analysis_requests.request_analysis(
                self.incident_id
            )

        self.assertEqual(
            result,
            {
                "incident_id": self.incident_id,
                "queued": False,
                "reason": "ALREADY_READY_OR_INACTIVE",
            },
        )

    def test_request_analysis_rejects_when_decision_disabled(self):
        with (
            patch.object(
                analysis_requests,
                "get_analysis_input",
                return_value=self.incident,
            ),
            patch.dict(
                os.environ,
                {"OCTV_DECISION_ENABLED": "0"},
                clear=False,
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                analysis_requests.request_analysis(
                    self.incident_id
                )

        self.assertEqual(
            context.exception.status_code,
            503,
        )

    def test_request_analysis_rejects_unsupported_hazard_before_lock(self):
        unsupported = {
            **self.incident,
            "hazard_type": "unsupported_hazard",
        }

        with (
            patch.object(
                analysis_requests,
                "get_analysis_input",
                return_value=unsupported,
            ),
            patch.object(
                analysis_requests,
                "acquire_analysis_lock",
            ) as acquire_lock,
            patch.dict(
                os.environ,
                {"OCTV_DECISION_ENABLED": "1"},
                clear=False,
            ),
        ):
            result = analysis_requests.request_analysis(
                self.incident_id
            )

        self.assertEqual(
            result["reason"],
            "UNSUPPORTED_HAZARD_TYPE",
        )
        acquire_lock.assert_not_called()

    def test_request_analysis_blocks_duplicate_lock(self):
        with (
            patch.object(
                analysis_requests,
                "get_analysis_input",
                return_value=self.incident,
            ),
            patch.object(
                analysis_requests,
                "acquire_analysis_lock",
                return_value=None,
            ),
            patch.dict(
                os.environ,
                {"OCTV_DECISION_ENABLED": "1"},
                clear=False,
            ),
        ):
            result = analysis_requests.request_analysis(
                self.incident_id
            )

        self.assertEqual(
            result,
            {
                "incident_id": self.incident_id,
                "queued": False,
                "reason": "ALREADY_QUEUED_OR_RUNNING",
            },
        )

    def test_request_analysis_publishes_task_with_lock_token(self):
        fake_task = types.SimpleNamespace(
            id="task-123"
        )
        delay = Mock(
            return_value=fake_task
        )

        fake_workers = types.ModuleType(
            "backend.app.workers"
        )
        fake_workers.analyze_incident = (
            types.SimpleNamespace(
                delay=delay
            )
        )

        with (
            patch.object(
                analysis_requests,
                "get_analysis_input",
                return_value=self.incident,
            ),
            patch.object(
                analysis_requests,
                "acquire_analysis_lock",
                return_value="lock-token",
            ),
            patch.object(
                analysis_requests,
                "release_analysis_lock",
            ) as release_lock,
            patch.dict(
                os.environ,
                {"OCTV_DECISION_ENABLED": "1"},
                clear=False,
            ),
            patch.dict(
                sys.modules,
                {
                    "backend.app.workers":
                        fake_workers
                },
            ),
        ):
            result = analysis_requests.request_analysis(
                self.incident_id
            )

        delay.assert_called_once_with(
            self.incident_id,
            "lock-token",
        )
        release_lock.assert_not_called()

        self.assertEqual(
            result,
            {
                "incident_id": self.incident_id,
                "queued": True,
                "task_id": "task-123",
            },
        )

    def test_publish_failure_releases_lock(self):
        delay = Mock(
            side_effect=RuntimeError(
                "publish failed"
            )
        )

        fake_workers = types.ModuleType(
            "backend.app.workers"
        )
        fake_workers.analyze_incident = (
            types.SimpleNamespace(
                delay=delay
            )
        )

        with (
            patch.object(
                analysis_requests,
                "get_analysis_input",
                return_value=self.incident,
            ),
            patch.object(
                analysis_requests,
                "acquire_analysis_lock",
                return_value="lock-token",
            ),
            patch.object(
                analysis_requests,
                "release_analysis_lock",
            ) as release_lock,
            patch.dict(
                os.environ,
                {"OCTV_DECISION_ENABLED": "1"},
                clear=False,
            ),
            patch.dict(
                sys.modules,
                {
                    "backend.app.workers":
                        fake_workers
                },
            ),
        ):
            with self.assertRaises(
                HTTPException
            ) as context:
                analysis_requests.request_analysis(
                    self.incident_id
                )

        self.assertEqual(
            context.exception.status_code,
            503,
        )

        release_lock.assert_called_once_with(
            self.incident_id,
            "lock-token",
        )

    def test_after_incident_committed_skips_when_disabled(self):
        with (
            patch.object(
                analysis_requests,
                "request_analysis",
            ) as request,
            patch.dict(
                os.environ,
                {"OCTV_DECISION_ENABLED": "0"},
                clear=False,
            ),
        ):
            result = (
                analysis_requests
                .after_incident_committed(
                    self.incident_id
                )
            )

        request.assert_not_called()

        self.assertEqual(
            result,
            {
                "incident_id": self.incident_id,
                "queued": False,
                "reason": "DISABLED",
            },
        )

    def test_after_incident_committed_does_not_propagate_queue_failure(self):
        with (
            patch.object(
                analysis_requests,
                "request_analysis",
                side_effect=RuntimeError(
                    "queue unavailable"
                ),
            ),
            patch.dict(
                os.environ,
                {"OCTV_DECISION_ENABLED": "1"},
                clear=False,
            ),
        ):
            result = (
                analysis_requests
                .after_incident_committed(
                    self.incident_id
                )
            )

        self.assertEqual(
            result,
            {
                "incident_id": self.incident_id,
                "queued": False,
            },
        )


if __name__ == "__main__":
    unittest.main()