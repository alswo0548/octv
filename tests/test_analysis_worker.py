import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from backend.app import workers


class FakeInsufficientContext(Exception):
    pass


class AnalysisWorkerTests(unittest.TestCase):
    def setUp(self):
        self.incident_id = 123
        self.lock_token = "lock-token"

    def _fake_ai_modules(self, run_pipeline):
        fake_config = types.ModuleType(
            "ai.config"
        )
        fake_config.get_runtime_config = Mock(
            return_value={"test": True}
        )

        fake_orchestration = types.ModuleType(
            "ai.orchestration"
        )
        fake_orchestration.__path__ = []

        fake_pipeline = types.ModuleType(
            "ai.orchestration.pipeline"
        )
        fake_pipeline.run_pipeline = (
            run_pipeline
        )

        fake_risk_priority = types.ModuleType(
            "ai.risk_priority"
        )
        fake_risk_priority.__path__ = []

        fake_rules = types.ModuleType(
            "ai.risk_priority.rules"
        )
        fake_rules.InsufficientContext = (
            FakeInsufficientContext
        )

        fake_orchestration.pipeline = (
            fake_pipeline
        )
        fake_risk_priority.rules = (
            fake_rules
        )

        return patch.dict(
            sys.modules,
            {
                "ai.config":
                    fake_config,
                "ai.orchestration":
                    fake_orchestration,
                "ai.orchestration.pipeline":
                    fake_pipeline,
                "ai.risk_priority":
                    fake_risk_priority,
                "ai.risk_priority.rules":
                    fake_rules,
            },
        )

    def _run_task(
        self,
        retries=0,
    ):
        task = workers.analyze_incident

        task.push_request(
            retries=retries
        )

        try:
            return task.run(
                self.incident_id,
                self.lock_token,
            )
        finally:
            task.pop_request()

    def test_disabled_releases_lock_and_skips(self):
        with (
            patch.dict(
                os.environ,
                {
                    "OCTV_DECISION_ENABLED":
                        "0"
                },
                clear=False,
            ),
            patch.object(
                workers,
                "_release_analysis_lock_safely",
            ) as release_lock,
        ):
            result = self._run_task()

        release_lock.assert_called_once_with(
            self.incident_id,
            self.lock_token,
        )

        self.assertEqual(
            result,
            {
                "incident_id":
                    self.incident_id,
                "skipped":
                    "DISABLED",
            },
        )

    def test_success_releases_lock(self):
        run_pipeline = Mock(
            return_value={
                "incident_id":
                    self.incident_id,
                "result":
                    "done",
            }
        )

        with (
            patch.dict(
                os.environ,
                {
                    "OCTV_DECISION_ENABLED":
                        "1"
                },
                clear=False,
            ),
            self._fake_ai_modules(
                run_pipeline
            ),
            patch.object(
                workers,
                "_release_analysis_lock_safely",
            ) as release_lock,
        ):
            result = self._run_task()

        run_pipeline.assert_called_once_with(
            self.incident_id,
            {"test": True},
        )

        release_lock.assert_called_once_with(
            self.incident_id,
            self.lock_token,
        )

        self.assertEqual(
            result["result"],
            "done",
        )

    def test_non_retryable_failure_releases_lock(self):
        run_pipeline = Mock(
            side_effect=ValueError(
                "unexpected failure"
            )
        )

        with (
            patch.dict(
                os.environ,
                {
                    "OCTV_DECISION_ENABLED":
                        "1"
                },
                clear=False,
            ),
            self._fake_ai_modules(
                run_pipeline
            ),
            patch.object(
                workers,
                "_release_analysis_lock_safely",
            ) as release_lock,
        ):
            with self.assertRaises(
                ValueError
            ):
                self._run_task()

        release_lock.assert_called_once_with(
            self.incident_id,
            self.lock_token,
        )

    def test_retryable_failure_keeps_lock_while_retrying(self):
        run_pipeline = Mock(
            side_effect=FakeInsufficientContext(
                "context unavailable"
            )
        )

        task = workers.analyze_incident

        with (
            patch.dict(
                os.environ,
                {
                    "OCTV_DECISION_ENABLED":
                        "1"
                },
                clear=False,
            ),
            self._fake_ai_modules(
                run_pipeline
            ),
            patch.object(
                workers,
                "_release_analysis_lock_safely",
            ) as release_lock,
            patch.object(
                task,
                "retry",
                side_effect=RuntimeError(
                    "retry scheduled"
                ),
            ) as retry,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "retry scheduled",
            ):
                self._run_task(
                    retries=0
                )

        release_lock.assert_not_called()

        retry.assert_called_once()

        self.assertEqual(
            retry.call_args.kwargs[
                "countdown"
            ],
            30,
        )

    def test_final_retry_failure_releases_lock(self):
        run_pipeline = Mock(
            side_effect=FakeInsufficientContext(
                "context unavailable"
            )
        )

        with (
            patch.dict(
                os.environ,
                {
                    "OCTV_DECISION_ENABLED":
                        "1"
                },
                clear=False,
            ),
            self._fake_ai_modules(
                run_pipeline
            ),
            patch.object(
                workers,
                "_release_analysis_lock_safely",
            ) as release_lock,
        ):
            with self.assertRaises(
                FakeInsufficientContext
            ):
                self._run_task(
                    retries=3
                )

        release_lock.assert_called_once_with(
            self.incident_id,
            self.lock_token,
        )

    def test_lock_release_failure_does_not_fail_completed_task(self):
        with patch.object(
            workers,
            "release_analysis_lock",
            side_effect=RuntimeError(
                "redis unavailable"
            ),
        ):
            workers._release_analysis_lock_safely(
                self.incident_id,
                self.lock_token,
            )


if __name__ == "__main__":
    unittest.main()