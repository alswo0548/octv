"""CCTV VERIFY 이전 모드를 Redis에 임시 보관합니다."""

from __future__ import annotations

import os

import redis


# ============================================================
# Redis Key
#
# Hash 구조:
#
# octv:cctv:verify_restore
#
# field:
#     CCTV ID
#
# value:
#     BASE / ALERT / POST_ALERT
#
# 예:
#
# HGETALL octv:cctv:verify_restore
#
# {
#     "1": "ALERT",
#     "2156": "BASE",
# }
# ============================================================

VERIFY_RESTORE_HASH_KEY = (
    "octv:cctv:verify_restore"
)


class RedisVerifyRestoreStore:
    """
    VERIFY 이전 감시 모드를 Redis에 저장한다.

    TTL은 사용하지 않는다.

    VERIFY 상태가 정상적으로 끝나거나
    재시작 복구가 끝났을 때 명시적으로 삭제한다.

    따라서:

    ALERT
        → Redis ALERT 기록
        → VERIFY
        → process crash

    상황에서도 다음 Runtime이
    ALERT를 복원할 수 있다.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        redis_client=None,
    ) -> None:

        # 테스트에서는 Fake Redis Client를
        # 직접 주입할 수 있다.
        if redis_client is not None:

            self._client = (
                redis_client
            )

            return

        resolved_url = (
            redis_url
            or os.environ.get(
                "OCTV_REDIS_URL"
            )
        )

        if not resolved_url:

            raise RuntimeError(
                "OCTV_REDIS_URL이 "
                "설정되어 있지 않습니다."
            )

        self._client = (
            redis.Redis.from_url(
                resolved_url,
                decode_responses=True,
            )
        )

    # ========================================================
    # Connection Check
    # ========================================================

    def ping(
        self,
    ) -> bool:

        return bool(
            self._client.ping()
        )

    # ========================================================
    # Save
    # ========================================================

    def save(
        self,
        cctv_id: int,
        restore_mode: str,
    ) -> None:

        self._client.hset(
            VERIFY_RESTORE_HASH_KEY,
            str(
                int(
                    cctv_id
                )
            ),
            str(
                restore_mode
            ).upper(),
        )

    # ========================================================
    # Delete
    # ========================================================

    def delete(
        self,
        cctv_id: int,
    ) -> None:

        self._client.hdel(
            VERIFY_RESTORE_HASH_KEY,
            str(
                int(
                    cctv_id
                )
            ),
        )

    # ========================================================
    # Load All
    # ========================================================

    def load_all(
        self,
    ) -> dict[
        int,
        str,
    ]:

        raw_values = (
            self._client.hgetall(
                VERIFY_RESTORE_HASH_KEY
            )
        )

        result: dict[
            int,
            str,
        ] = {}

        for (
            raw_cctv_id,
            raw_restore_mode,
        ) in raw_values.items():

            try:

                cctv_id = int(
                    raw_cctv_id
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise RuntimeError(
                    "Redis VERIFY 복구 정보에 "
                    "잘못된 CCTV ID가 있습니다. "
                    f"value={raw_cctv_id}"
                ) from exc

            restore_mode = str(
                raw_restore_mode
            ).upper()

            result[
                cctv_id
            ] = restore_mode

        return result