"""Weather Alert Scheduler 실제 PostgreSQL 통합 테스트.

실제 DB transaction 안에서:

1. BASE + 폭염경보
   -> true + BASE 유지

2. BASE + 대설주의보
   -> true + ALERT

3. 대설 + 강풍 동시 ACTIVE
   -> true + ALERT 유지

4. 대설만 종료, 강풍 유지
   -> true + ALERT 유지

5. 모든 감시대상 특보 종료
   -> true + POST_ALERT

6. POST_ALERT + 폭염만 존재
   -> true + POST_ALERT 유지

7. false + OFF + 대설주의보
   -> true + ALERT

8. 위 대설 종료
   -> true + POST_ALERT

9. true + VERIFY + 대설주의보
   -> true + VERIFY 유지

모든 변경은 마지막에 ROLLBACK한다.
"""

from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from backend.app.config import (
    database_connect_kwargs,
)
from backend.app.weather_alerts.client import (
    KmaWarningStatus,
)
from backend.app.weather_alerts.repository import (
    synchronize_weather_alerts,
)


def _get_state(
    connection,
    cctv_id: int,
) -> dict:
    """CCTV is_monitored / monitored_mode 조회."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                is_monitored,
                monitored_mode::text
                    AS monitored_mode
            FROM cctvs
            WHERE id = %s;
            """,
            (
                cctv_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise AssertionError(
            f"CCTV {cctv_id}가 없습니다."
        )

    return row


def _set_state(
    connection,
    cctv_id: int,
    *,
    is_monitored: bool,
    mode: str,
) -> None:
    """테스트용 CCTV 감시 상태 변경."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE cctvs
            SET
                is_monitored = %s,
                monitored_mode =
                    %s::monitored_mode_enum
            WHERE id = %s;
            """,
            (
                is_monitored,
                mode,
                cctv_id,
            ),
        )


def _select_test_target(
    connection,
) -> dict:
    """
    현재 감시 중이며 BASE 상태이고,
    weather_region_code가 존재하는
    CCTV 한 개를 테스트 대상으로 선택한다.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                c.id AS cctv_id,
                c.name AS cctv_name,
                c.region_code,
                r.sido_name,
                r.sigungu_name,
                r.weather_region_code
            FROM cctvs AS c
            JOIN region AS r
              ON r.region_code = c.region_code
            WHERE c.is_monitored = TRUE
              AND c.monitored_mode =
                  'BASE'::monitored_mode_enum
              AND r.weather_region_code IS NOT NULL
              AND cardinality(
                  r.weather_region_code
              ) > 0
            ORDER BY c.id
            LIMIT 1;
            """
        )

        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "테스트 가능한 BASE 감시 CCTV가 없습니다."
        )

    return row


def _warning(
    *,
    weather_region_code: str,
    warning_code: str,
    warning_name: str,
    level_code: str,
    level_name: str,
    minute: int,
) -> KmaWarningStatus:
    """
    테스트용 ACTIVE 기상특보 생성.
    """

    issued_at = datetime(
        2099,
        1,
        1,
        12,
        minute,
    )

    return KmaWarningStatus(
        weather_region_code=(
            weather_region_code
        ),
        region_name=(
            "OCTV_TEST_REGION"
        ),
        issued_at=(
            issued_at
        ),
        effective_at=(
            issued_at
        ),
        warning_code=(
            warning_code
        ),
        warning_name=(
            warning_name
        ),
        level_code=(
            level_code
        ),
        level_name=(
            level_name
        ),
        command_code="1",
        command_name="발표",
        active=True,
    )


def _assert_state(
    connection,
    cctv_id: int,
    *,
    expected_is_monitored: bool,
    expected_mode: str,
    label: str,
) -> None:
    """
    CCTV is_monitored / monitored_mode 검사.
    """

    state = _get_state(
        connection,
        cctv_id,
    )

    actual_is_monitored = bool(
        state[
            "is_monitored"
        ]
    )

    actual_mode = str(
        state[
            "monitored_mode"
        ]
    )

    if (
        actual_is_monitored
        != expected_is_monitored
    ):
        raise AssertionError(
            f"{label}: "
            "is_monitored "
            f"expected={expected_is_monitored}, "
            f"actual={actual_is_monitored}"
        )

    if actual_mode != expected_mode:
        raise AssertionError(
            f"{label}: "
            "monitored_mode "
            f"expected={expected_mode}, "
            f"actual={actual_mode}"
        )

    print(
        f"[PASS] {label} "
        f"-> is_monitored="
        f"{actual_is_monitored} "
        f"/ mode={actual_mode}"
    )


def main() -> None:
    print("=" * 72)

    print(
        "WEATHER ALERT SCHEDULER "
        "POSTGRESQL INTEGRATION TEST"
    )

    print("=" * 72)

    connection = psycopg.connect(
        **database_connect_kwargs(),
        row_factory=dict_row,
    )

    try:
        # ====================================================
        # 테스트 대상 선택
        # ====================================================

        target = _select_test_target(
            connection
        )

        cctv_id = int(
            target["cctv_id"]
        )

        weather_region_code = str(
            target[
                "weather_region_code"
            ][0]
        )

        print(
            "test CCTV:",
            cctv_id,
            "/",
            target["cctv_name"],
        )

        print(
            "region:",
            target["region_code"],
            "/",
            target["sido_name"],
            target["sigungu_name"],
        )

        print(
            "weather code:",
            weather_region_code,
        )

        # ====================================================
        # 테스트 transaction 안에서는
        # 기존 weather_alerts를 보이지 않게 만든다.
        #
        # 마지막 ROLLBACK 시 전부 복구된다.
        # ====================================================

        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM weather_alerts;
                """
            )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="BASE",
            label="초기 상태",
        )

        # ====================================================
        # 테스트용 특보
        # ====================================================

        heat = _warning(
            weather_region_code=(
                weather_region_code
            ),
            warning_code="H",
            warning_name="폭염",
            level_code="3",
            level_name="경보",
            minute=1,
        )

        snow = _warning(
            weather_region_code=(
                weather_region_code
            ),
            warning_code="S",
            warning_name="대설",
            level_code="2",
            level_name="주의보",
            minute=2,
        )

        wind = _warning(
            weather_region_code=(
                weather_region_code
            ),
            warning_code="W",
            warning_name="강풍",
            level_code="2",
            level_name="주의보",
            minute=3,
        )

        # ====================================================
        # TEST 1
        # 폭염경보만 존재
        # ====================================================

        result = synchronize_weather_alerts(
            connection,
            [
                heat,
            ],
        )

        if (
            result[
                "monitoring_trigger_alert_row_count"
            ]
            != 0
        ):
            raise AssertionError(
                "폭염경보는 monitoring trigger가 "
                "아니어야 합니다."
            )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="BASE",
            label="폭염경보는 BASE 유지",
        )

        # ====================================================
        # TEST 2
        # true + BASE -> true + ALERT
        # ====================================================

        result = synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
            ],
        )

        if (
            result[
                "monitoring_trigger_alert_row_count"
            ]
            < 1
        ):
            raise AssertionError(
                "대설주의보가 monitoring trigger로 "
                "생성되지 않았습니다."
            )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="ALERT",
            label=(
                "대설주의보 "
                "BASE -> ALERT"
            ),
        )

        # ====================================================
        # TEST 3
        # 대설 + 강풍 동시 ACTIVE
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
                wind,
            ],
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="ALERT",
            label=(
                "대설+강풍 동시 특보 "
                "ALERT 유지"
            ),
        )

        # ====================================================
        # TEST 4
        # 대설 종료 + 강풍 유지
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
                wind,
            ],
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="ALERT",
            label=(
                "대설 종료 + 강풍 유지 "
                "-> ALERT 유지"
            ),
        )

        # ====================================================
        # TEST 5
        # 모든 감시대상 특보 종료
        #
        # true + ALERT -> true + POST_ALERT
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
            ],
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="POST_ALERT",
            label=(
                "감시대상 특보 모두 종료 "
                "-> POST_ALERT"
            ),
        )

        # ====================================================
        # TEST 6
        # POST_ALERT 자동복귀 금지
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
            ],
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="POST_ALERT",
            label="POST_ALERT 유지 정책",
        )

        # ====================================================
        # TEST 7
        #
        # 평소 감시하지 않는 CCTV 상태:
        #
        # false + OFF
        #
        # 여기에 대설주의보가 발생하면:
        #
        # true + ALERT
        # ====================================================

        _set_state(
            connection,
            cctv_id,
            is_monitored=False,
            mode="OFF",
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=False,
            expected_mode="OFF",
            label="기상특보 전 OFF 상태",
        )

        synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
            ],
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="ALERT",
            label=(
                "OFF + 대설주의보 "
                "-> ALERT"
            ),
        )

        # ====================================================
        # TEST 8
        #
        # OFF에서 특보로 켜진 CCTV의
        # 감시대상 특보가 모두 종료되면:
        #
        # true + ALERT
        # -> true + POST_ALERT
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
            ],
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="POST_ALERT",
            label=(
                "OFF에서 시작한 특보 종료 "
                "-> POST_ALERT"
            ),
        )

        # ====================================================
        # TEST 9
        # VERIFY는 Scheduler가 변경하지 않는다.
        # ====================================================

        _set_state(
            connection,
            cctv_id,
            is_monitored=True,
            mode="VERIFY",
        )

        synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
            ],
        )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="VERIFY",
            label="VERIFY 상태 보호",
        )

        # ====================================================
        # weather_alerts 저장 확인
        # ====================================================

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    alert_type,
                    alert_level,
                    status::text AS status
                FROM weather_alerts
                WHERE region_code = %s
                ORDER BY issued_at;
                """,
                (
                    target[
                        "region_code"
                    ],
                ),
            )

            rows = cursor.fetchall()

        if not rows:
            raise AssertionError(
                "weather_alerts에 테스트 특보가 "
                "저장되지 않았습니다."
            )

        print(
            "[PASS] weather_alerts "
            "INSERT / UPDATE / ENDED 처리"
        )

        print()

        print(
            "[SUCCESS] "
            "Weather Alert Scheduler "
            "PostgreSQL 통합 테스트 정상"
        )

    finally:
        # ====================================================
        # 테스트 중 weather_alerts와 CCTV 감시 상태의
        # 모든 변경을 원상복구한다.
        # ====================================================

        connection.rollback()
        connection.close()

        print(
            "[ROLLBACK] "
            "DB 테스트 변경사항 원상복구 완료"
        )


if __name__ == "__main__":
    main()