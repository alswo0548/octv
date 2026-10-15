"""Weather Alert Scheduler 실제 PostgreSQL 통합 테스트.

실제 DB transaction 안에서:

1. BASE + 폭염경보
   -> BASE 유지

2. BASE + 대설주의보
   -> ALERT

3. 대설 + 강풍 동시 ACTIVE
   -> ALERT

4. 대설만 종료, 강풍 유지
   -> ALERT 유지

5. 모든 감시대상 특보 종료
   -> POST_ALERT

6. POST_ALERT + 폭염만 존재
   -> POST_ALERT 유지
   -> BASE 자동복귀 금지 확인

7. OFF + 대설주의보
   -> OFF 유지

8. VERIFY + 대설주의보
   -> VERIFY 유지

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


def _get_mode(
    connection,
    cctv_id: int,
) -> str:
    """CCTV monitored_mode 조회."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT monitored_mode::text
            FROM cctvs
            WHERE id = %s;
            """,
            (cctv_id,),
        )

        row = cursor.fetchone()

    if row is None:
        raise AssertionError(
            f"CCTV {cctv_id}가 없습니다."
        )

    return row["monitored_mode"]


def _set_mode(
    connection,
    cctv_id: int,
    mode: str,
) -> None:
    """테스트용 monitored_mode 변경."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE cctvs
            SET monitored_mode =
                %s::monitored_mode_enum
            WHERE id = %s;
            """,
            (
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


def _assert_mode(
    connection,
    cctv_id: int,
    expected: str,
    label: str,
) -> None:
    """
    CCTV mode 검사.
    """

    actual = _get_mode(
        connection,
        cctv_id,
    )

    if actual != expected:
        raise AssertionError(
            f"{label}: "
            f"expected={expected}, "
            f"actual={actual}"
        )

    print(
        f"[PASS] {label} "
        f"-> {actual}"
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
        # 아직 COMMIT하지 않으므로
        # 다른 DB connection에서는 영향을 받지 않는다.
        #
        # 마지막 ROLLBACK 시 전부 복구된다.
        # ====================================================

        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM weather_alerts;
                """
            )

        _assert_mode(
            connection,
            cctv_id,
            "BASE",
            "초기 상태",
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
        #
        # 폭염은 weather_alerts 기록 대상이지만
        # CCTV ALERT 트리거는 아니다.
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

        _assert_mode(
            connection,
            cctv_id,
            "BASE",
            "폭염경보는 BASE 유지",
        )

        # ====================================================
        # TEST 2
        # 대설주의보 발생
        #
        # BASE -> ALERT
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

        _assert_mode(
            connection,
            cctv_id,
            "ALERT",
            "대설주의보 BASE -> ALERT",
        )

        # ====================================================
        # TEST 3
        # 대설 + 강풍 동시 ACTIVE
        #
        # ALERT 유지
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
                wind,
            ],
        )

        _assert_mode(
            connection,
            cctv_id,
            "ALERT",
            "대설+강풍 동시 특보 ALERT 유지",
        )

        # ====================================================
        # TEST 4
        # 대설 종료
        # 강풍은 여전히 ACTIVE
        #
        # 같은 지역에 감시대상 특보가 남아 있으므로
        # ALERT 유지
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
                wind,
            ],
        )

        _assert_mode(
            connection,
            cctv_id,
            "ALERT",
            "대설 종료 + 강풍 유지 -> ALERT 유지",
        )

        # ====================================================
        # TEST 5
        # 강풍까지 종료
        #
        # 폭염만 남음.
        #
        # ALERT -> POST_ALERT
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
            ],
        )

        _assert_mode(
            connection,
            cctv_id,
            "POST_ALERT",
            "감시대상 특보 모두 종료 -> POST_ALERT",
        )

        # ====================================================
        # TEST 6
        # 폭염만 계속 존재
        #
        # POST_ALERT -> BASE 자동복귀 금지
        # ====================================================

        synchronize_weather_alerts(
            connection,
            [
                heat,
            ],
        )

        _assert_mode(
            connection,
            cctv_id,
            "POST_ALERT",
            "POST_ALERT 수동복귀 정책",
        )

        # ====================================================
        # TEST 7
        # OFF 상태에서는 대설이 와도 OFF 유지
        # ====================================================

        _set_mode(
            connection,
            cctv_id,
            "OFF",
        )

        synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
            ],
        )

        _assert_mode(
            connection,
            cctv_id,
            "OFF",
            "OFF 상태 보호",
        )

        # ====================================================
        # TEST 8
        # VERIFY 상태에서는 대설이 와도 VERIFY 유지
        # ====================================================

        _set_mode(
            connection,
            cctv_id,
            "VERIFY",
        )

        synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
            ],
        )

        _assert_mode(
            connection,
            cctv_id,
            "VERIFY",
            "VERIFY 상태 보호",
        )

        # ====================================================
        # weather_alerts 저장 자체도 확인
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
        # 중요:
        #
        # 테스트 중 weather_alerts와 CCTV mode의
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