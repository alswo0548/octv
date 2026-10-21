from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest.mock import patch

from ai.detection.incident_runtime import (
    IncidentAwareCctvDetectionRuntime,
)

from ai.detection.verify_restore_store import (
    RedisVerifyRestoreStore,
    VERIFY_RESTORE_HASH_KEY,
)

from backend.app.cctvs import (
    repository as cctv_repository,
)


# ============================================================
# Fake Redis
# ============================================================


class FakeRedis:
    def __init__(
        self,
    ) -> None:

        self._hashes: dict[
            str,
            dict[
                str,
                str,
            ],
        ] = {}

    def ping(
        self,
    ) -> bool:

        return True

    def hset(
        self,
        name: str,
        key: str,
        value: str,
    ) -> int:

        target = (
            self
            ._hashes
            .setdefault(
                name,
                {},
            )
        )

        is_new = (
            key
            not in target
        )

        target[
            key
        ] = value

        return (
            1
            if is_new
            else 0
        )

    def hdel(
        self,
        name: str,
        key: str,
    ) -> int:

        target = (
            self
            ._hashes
            .get(
                name,
                {},
            )
        )

        if key not in target:
            return 0

        del target[
            key
        ]

        return 1

    def hgetall(
        self,
        name: str,
    ) -> dict[
        str,
        str,
    ]:

        return dict(
            self
            ._hashes
            .get(
                name,
                {},
            )
        )


# ============================================================
# Fake DB Connection
# ============================================================


@contextmanager
def fake_get_connection():

    yield object()


# ============================================================
# Tests
# ============================================================


class VerifyRestartRecoveryTests(
    unittest.TestCase
):

    # ========================================================
    # Redis Store 기본 동작
    # ========================================================

    def test_redis_store_save_load_delete(
        self,
    ) -> None:

        fake_redis = FakeRedis()

        store = (
            RedisVerifyRestoreStore(
                redis_client=(
                    fake_redis
                )
            )
        )

        self.assertTrue(
            store.ping()
        )

        store.save(
            cctv_id=1,
            restore_mode="ALERT",
        )

        self.assertEqual(
            store.load_all(),
            {
                1: "ALERT",
            },
        )

        self.assertEqual(
            fake_redis.hgetall(
                VERIFY_RESTORE_HASH_KEY
            ),
            {
                "1": "ALERT",
            },
        )

        store.delete(
            1
        )

        self.assertEqual(
            store.load_all(),
            {},
        )

    # ========================================================
    # ALERT → VERIFY 직전 Redis Journal 저장
    # ========================================================

    def test_remember_restore_mode_writes_redis(
        self,
    ) -> None:

        fake_redis = FakeRedis()

        store = (
            RedisVerifyRestoreStore(
                redis_client=(
                    fake_redis
                )
            )
        )

        runtime = object.__new__(
            IncidentAwareCctvDetectionRuntime
        )

        runtime._verify_restore_store = (
            store
        )

        runtime._verify_restore_mode_by_cctv = {}

        runtime._remember_verify_restore_mode(
            cctv_id=1,
            restore_mode="ALERT",
        )

        self.assertEqual(
            runtime
            ._verify_restore_mode_by_cctv,
            {
                1: "ALERT",
            },
        )

        self.assertEqual(
            store.load_all(),
            {
                1: "ALERT",
            },
        )

    # ========================================================
    # Crash 후 restart
    #
    # Redis:
    #   1 → ALERT
    #
    # DB:
    #   1 → VERIFY
    #
    # Runtime 재시작:
    #   VERIFY → ALERT
    # ========================================================

    def test_restart_restores_stale_verify(
        self,
    ) -> None:

        fake_redis = FakeRedis()

        store = (
            RedisVerifyRestoreStore(
                redis_client=(
                    fake_redis
                )
            )
        )

        # 이전 Runtime이 남긴 Journal.
        store.save(
            cctv_id=1,
            restore_mode="ALERT",
        )

        # DB에는 VERIFY가 그대로 남아 있는 상황.
        state = {
            "mode":
                "VERIFY",
        }

        runtime = object.__new__(
            IncidentAwareCctvDetectionRuntime
        )

        runtime._verify_restore_store = (
            store
        )

        runtime._verify_restore_mode_by_cctv = {}

        def fake_restore_from_verify_mode(
            connection,
            cctv_id: int,
            restore_mode: str,
        ):

            self.assertEqual(
                cctv_id,
                1,
            )

            self.assertEqual(
                restore_mode,
                "ALERT",
            )

            if (
                state[
                    "mode"
                ]
                != "VERIFY"
            ):

                return None

            state[
                "mode"
            ] = restore_mode

            return {
                "id":
                    cctv_id,

                "monitored_mode":
                    restore_mode,
            }

        with (
            patch(
                "ai.detection.incident_runtime.get_connection",
                new=fake_get_connection,
            ),
            patch.object(
                cctv_repository,
                "restore_from_verify_mode",
                side_effect=(
                    fake_restore_from_verify_mode
                ),
            ),
        ):

            runtime._recover_stale_verify_modes()

        self.assertEqual(
            state[
                "mode"
            ],
            "ALERT",
        )

        self.assertEqual(
            store.load_all(),
            {},
        )

    # ========================================================
    # Redis Journal은 남았지만
    # DB가 이미 VERIFY가 아닌 경우
    #
    # DB 상태를 덮어쓰지 않는다.
    # ========================================================

    def test_restart_does_not_overwrite_changed_db_mode(
        self,
    ) -> None:

        fake_redis = FakeRedis()

        store = (
            RedisVerifyRestoreStore(
                redis_client=(
                    fake_redis
                )
            )
        )

        store.save(
            cctv_id=1,
            restore_mode="ALERT",
        )

        # crash 이후 다른 로직 또는 운영자가
        # POST_ALERT로 이미 변경한 상황.
        state = {
            "mode":
                "POST_ALERT",
        }

        runtime = object.__new__(
            IncidentAwareCctvDetectionRuntime
        )

        runtime._verify_restore_store = (
            store
        )

        runtime._verify_restore_mode_by_cctv = {}

        def fake_restore_from_verify_mode(
            connection,
            cctv_id: int,
            restore_mode: str,
        ):

            if (
                state[
                    "mode"
                ]
                != "VERIFY"
            ):

                return None

            state[
                "mode"
            ] = restore_mode

            return {
                "id":
                    cctv_id,

                "monitored_mode":
                    restore_mode,
            }

        with (
            patch(
                "ai.detection.incident_runtime.get_connection",
                new=fake_get_connection,
            ),
            patch.object(
                cctv_repository,
                "restore_from_verify_mode",
                side_effect=(
                    fake_restore_from_verify_mode
                ),
            ),
        ):

            runtime._recover_stale_verify_modes()

        # 기존 POST_ALERT를 ALERT로 덮어쓰면 안 됨.
        self.assertEqual(
            state[
                "mode"
            ],
            "POST_ALERT",
        )

        # 더 이상 복구할 VERIFY가 아니므로
        # stale Redis Journal은 삭제.
        self.assertEqual(
            store.load_all(),
            {},
        )


if __name__ == "__main__":

    unittest.main(
        verbosity=2
    )