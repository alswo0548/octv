import unittest
from unittest.mock import Mock, patch

from backend.app import analysis_lock


class AnalysisLockTests(unittest.TestCase):
    def test_acquire_returns_token_when_lock_created(self):
        client = Mock()
        client.set.return_value = True

        with patch.object(
            analysis_lock,
            "_get_redis_client",
            return_value=client,
        ):
            token = analysis_lock.acquire_analysis_lock(
                123
            )

        self.assertIsInstance(
            token,
            str,
        )
        self.assertTrue(token)

        client.set.assert_called_once_with(
            "octv:analysis:incident:123",
            token,
            nx=True,
            ex=analysis_lock.ANALYSIS_LOCK_TTL_SEC,
        )

    def test_acquire_returns_none_when_lock_already_exists(self):
        client = Mock()
        client.set.return_value = False

        with patch.object(
            analysis_lock,
            "_get_redis_client",
            return_value=client,
        ):
            token = analysis_lock.acquire_analysis_lock(
                123
            )

        self.assertIsNone(token)

    def test_release_returns_false_without_token(self):
        with patch.object(
            analysis_lock,
            "_get_redis_client",
        ) as get_client:
            released = (
                analysis_lock
                .release_analysis_lock(
                    123,
                    None,
                )
            )

        self.assertFalse(released)
        get_client.assert_not_called()

    def test_release_returns_true_when_owned_lock_deleted(self):
        client = Mock()
        client.eval.return_value = 1

        with patch.object(
            analysis_lock,
            "_get_redis_client",
            return_value=client,
        ):
            released = (
                analysis_lock
                .release_analysis_lock(
                    123,
                    "lock-token",
                )
            )

        self.assertTrue(released)

        client.eval.assert_called_once_with(
            analysis_lock._RELEASE_LOCK_SCRIPT,
            1,
            "octv:analysis:incident:123",
            "lock-token",
        )

    def test_release_returns_false_when_token_does_not_match(self):
        client = Mock()
        client.eval.return_value = 0

        with patch.object(
            analysis_lock,
            "_get_redis_client",
            return_value=client,
        ):
            released = (
                analysis_lock
                .release_analysis_lock(
                    123,
                    "wrong-token",
                )
            )

        self.assertFalse(released)


if __name__ == "__main__":
    unittest.main()