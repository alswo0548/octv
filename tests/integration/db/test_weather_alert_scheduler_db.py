"""Weather Alert Scheduler 실제 PostgreSQL 통합 테스트.

실제 DB transaction 안에서:

1. BASE + 폭염경보
   -> true + BASE 유지

2. BASE + 대설주의보
   -> 집중감시 슬롯 1대만 ALERT

3. 대설 + 강풍 동시 ACTIVE
   -> ALERT 1대 유지

4. 대설만 종료, 강풍 유지
   -> ALERT 1대 유지

5. 모든 감시대상 특보 종료
   -> true + POST_ALERT

6. POST_ALERT + 폭염만 존재
   -> true + POST_ALERT 유지

7. false + OFF + 대설주의보
   -> OFF CCTV 우선 ALERT

8. 위 대설 종료
   -> true + POST_ALERT

9. true + VERIFY + 대설주의보
   -> VERIFY가 집중감시 슬롯을 유지
   -> 추가 ALERT 생성 금지

테스트용 weather_region_code가 여러 OCTV region_code에
매핑될 수 있으므로, 해당 특보 코드의 전체 매핑 범위를
하나의 테스트 scope로 격리한다.

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


def _select_test_scope(
    connection,
) -> dict:
    """
    하나의 기상특보 코드가 매핑되는 전체 OCTV 지역을
    테스트 scope로 선택한다.

    VERIFY 상태에서 다른 CCTV가 추가 ALERT로
    올라가지 않는 것까지 검사해야 하므로,
    scope 안에 UTIC CCTV가 최소 2대 존재하는
    weather_region_code를 선택한다.

    scope 안에서 가장 작은 CCTV id를
    기준 테스트 CCTV로 사용한다.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH weather_scopes AS (
                SELECT
                    w.weather_code,
                    array_agg(
                        DISTINCT r.region_code
                        ORDER BY r.region_code
                    ) AS region_codes
                FROM region AS r
                CROSS JOIN LATERAL
                    unnest(
                        r.weather_region_code
                    )
                    AS w(weather_code)
                WHERE r.weather_region_code
                      IS NOT NULL
                  AND cardinality(
                      r.weather_region_code
                  ) > 0
                GROUP BY
                    w.weather_code
            ),

            scopes_with_cctv AS (
                SELECT
                    ws.weather_code,
                    ws.region_codes,
                    COUNT(c.id)
                        AS cctv_count,
                    MIN(c.id)
                        AS cctv_id
                FROM weather_scopes AS ws
                JOIN cctvs AS c
                  ON c.region_code =
                     ANY(
                         ws.region_codes
                     )
                 AND c.provider = 'UTIC'
                 AND c.external_cctv_id
                     IS NOT NULL
                GROUP BY
                    ws.weather_code,
                    ws.region_codes
                HAVING COUNT(c.id) >= 2
            )

            SELECT
                s.weather_code,
                s.region_codes,
                s.cctv_count,
                c.id AS cctv_id,
                c.name AS cctv_name,
                c.region_code,
                r.sido_name,
                r.sigungu_name
            FROM scopes_with_cctv AS s
            JOIN cctvs AS c
              ON c.id = s.cctv_id
            JOIN region AS r
              ON r.region_code =
                 c.region_code
            ORDER BY
                cardinality(
                    s.region_codes
                ),
                s.weather_code,
                c.id
            LIMIT 1;
            """
        )

        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Weather Scheduler 통합 테스트에 사용할 "
            "UTIC CCTV 2대 이상 특보 범위를 "
            "찾을 수 없습니다."
        )

    return row


def _prepare_scope_as_base(
    connection,
    region_codes: list[str],
) -> None:
    """
    테스트 대상 weather_region_code에 매핑되는
    전체 UTIC CCTV를 true + BASE로 통일한다.

    이렇게 해야 실제 DB의 현재 ALERT / VERIFY / OFF 상태가
    테스트 결과에 영향을 주지 않는다.

    마지막에 transaction 전체를 rollback하므로
    실제 운영 상태는 변경되지 않는다.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE cctvs
            SET
                is_monitored = TRUE,
                monitored_mode =
                    'BASE'
                    ::monitored_mode_enum
            WHERE region_code =
                  ANY(
                      %s::varchar[]
                  )
              AND provider = 'UTIC'
              AND external_cctv_id
                  IS NOT NULL;
            """,
            (
                region_codes,
            ),
        )


def _list_focus_cctvs(
    connection,
    region_codes: list[str],
) -> list[dict]:
    """
    테스트 scope에서 현재 집중감시 슬롯에 해당하는
    ALERT / VERIFY CCTV를 조회한다.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                name,
                region_code,
                is_monitored,
                monitored_mode::text
                    AS monitored_mode
            FROM cctvs
            WHERE region_code =
                  ANY(
                      %s::varchar[]
                  )
              AND provider = 'UTIC'
              AND external_cctv_id
                  IS NOT NULL
              AND is_monitored = TRUE
              AND monitored_mode IN (
                  'ALERT'
                  ::monitored_mode_enum,
                  'VERIFY'
                  ::monitored_mode_enum
              )
            ORDER BY id;
            """,
            (
                region_codes,
            ),
        )

        return cursor.fetchall()


def _assert_single_focus(
    connection,
    region_codes: list[str],
    *,
    expected_cctv_id: int,
    expected_mode: str,
    label: str,
) -> None:
    """
    테스트 scope 안의 ALERT / VERIFY 집중감시 슬롯이
    정확히 1대인지 확인한다.
    """

    rows = _list_focus_cctvs(
        connection,
        region_codes,
    )

    if len(rows) != 1:
        raise AssertionError(
            f"{label}: "
            "집중감시 CCTV는 정확히 1대여야 합니다. "
            f"actual={len(rows)}, "
            f"rows={rows}"
        )

    row = rows[0]

    actual_cctv_id = int(
        row["id"]
    )

    actual_mode = str(
        row["monitored_mode"]
    )

    if (
        actual_cctv_id
        != expected_cctv_id
    ):
        raise AssertionError(
            f"{label}: "
            "예상 CCTV가 집중감시 슬롯을 "
            "사용하지 않고 있습니다. "
            f"expected={expected_cctv_id}, "
            f"actual={actual_cctv_id}"
        )

    if actual_mode != expected_mode:
        raise AssertionError(
            f"{label}: "
            "집중감시 모드가 다릅니다. "
            f"expected={expected_mode}, "
            f"actual={actual_mode}"
        )

    print(
        f"[PASS] {label} "
        f"-> CCTV {actual_cctv_id} "
        f"/ mode={actual_mode}"
    )


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
        # 테스트 scope 선택
        # ====================================================

        target = _select_test_scope(
            connection
        )

        cctv_id = int(
            target["cctv_id"]
        )

        weather_region_code = str(
            target[
                "weather_code"
            ]
        )

        region_codes = [
            str(region_code)
            for region_code
            in target[
                "region_codes"
            ]
        ]

        print(
            "test CCTV:",
            cctv_id,
            "/",
            target["cctv_name"],
        )

        print(
            "target region:",
            target["region_code"],
            "/",
            target["sido_name"],
            target["sigungu_name"],
        )

        print(
            "weather code:",
            weather_region_code,
        )

        print(
            "weather scope regions:",
            len(region_codes),
            "/",
            region_codes,
        )

        print(
            "scope UTIC CCTV count:",
            target["cctv_count"],
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

        # ====================================================
        # 운영 DB의 현재 CCTV 상태와 관계없이
        # 테스트 scope를 BASE 상태로 격리한다.
        # ====================================================

        _prepare_scope_as_base(
            connection,
            region_codes,
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

        if _list_focus_cctvs(
            connection,
            region_codes,
        ):
            raise AssertionError(
                "폭염경보만 존재할 때 "
                "ALERT / VERIFY CCTV가 "
                "생기면 안 됩니다."
            )

        print(
            "[PASS] 폭염경보 "
            "집중감시 슬롯 미사용"
        )

        # ====================================================
        # TEST 2
        # true + BASE -> true + ALERT
        #
        # scope 전체가 BASE이고,
        # 가장 작은 id인 cctv_id가 선택된다.
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

        if (
            result[
                "cctv_to_alert_count"
            ]
            != 1
        ):
            raise AssertionError(
                "대설주의보 최초 발생 시 "
                "ALERT CCTV는 1대만 "
                "생성되어야 합니다. "
                f"actual="
                f"{result['cctv_to_alert_count']}"
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

        _assert_single_focus(
            connection,
            region_codes,
            expected_cctv_id=(
                cctv_id
            ),
            expected_mode="ALERT",
            label=(
                "대설주의보 단일 "
                "ALERT 슬롯"
            ),
        )

        # ====================================================
        # TEST 3
        # 대설 + 강풍 동시 ACTIVE
        # ====================================================

        result = synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
                wind,
            ],
        )

        if (
            result[
                "cctv_to_alert_count"
            ]
            != 0
        ):
            raise AssertionError(
                "이미 ALERT 슬롯이 있는데 "
                "추가 ALERT가 생성되었습니다."
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

        _assert_single_focus(
            connection,
            region_codes,
            expected_cctv_id=(
                cctv_id
            ),
            expected_mode="ALERT",
            label=(
                "대설+강풍 "
                "단일 집중감시 슬롯"
            ),
        )

        # ====================================================
        # TEST 4
        # 대설 종료 + 강풍 유지
        # ====================================================

        result = synchronize_weather_alerts(
            connection,
            [
                heat,
                wind,
            ],
        )

        if (
            result[
                "cctv_to_alert_count"
            ]
            != 0
        ):
            raise AssertionError(
                "강풍 특보가 계속 ACTIVE인데 "
                "새 ALERT CCTV가 생성되었습니다."
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

        _assert_single_focus(
            connection,
            region_codes,
            expected_cctv_id=(
                cctv_id
            ),
            expected_mode="ALERT",
            label=(
                "강풍 유지 중 "
                "단일 ALERT 슬롯"
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
        # 다른 scope CCTV들은 BASE.
        #
        # 특보 발생 시 OFF 우선 정책 때문에
        # cctv_id가 다시 ALERT가 되어야 한다.
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

        result = synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
            ],
        )

        if (
            result[
                "cctv_to_alert_count"
            ]
            != 1
        ):
            raise AssertionError(
                "OFF CCTV 우선 선택에서 "
                "ALERT 1대가 생성되어야 합니다. "
                f"actual="
                f"{result['cctv_to_alert_count']}"
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

        _assert_single_focus(
            connection,
            region_codes,
            expected_cctv_id=(
                cctv_id
            ),
            expected_mode="ALERT",
            label=(
                "OFF 우선 선택 후 "
                "단일 ALERT 슬롯"
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
        #
        # Incident Runtime이:
        #
        # ALERT -> VERIFY
        #
        # 로 일시 전환한 상황을 재현한다.
        #
        # Scheduler는 VERIFY를 기존 집중감시 슬롯으로
        # 인식해야 하므로 다른 BASE CCTV를
        # 새 ALERT로 추가하면 안 된다.
        # ====================================================

        _set_state(
            connection,
            cctv_id,
            is_monitored=True,
            mode="VERIFY",
        )

        result = synchronize_weather_alerts(
            connection,
            [
                heat,
                snow,
            ],
        )

        if (
            result[
                "cctv_to_alert_count"
            ]
            != 0
        ):
            raise AssertionError(
                "VERIFY CCTV가 이미 집중감시 슬롯을 "
                "사용 중인데 추가 ALERT가 "
                "생성되었습니다. "
                f"actual="
                f"{result['cctv_to_alert_count']}"
            )

        _assert_state(
            connection,
            cctv_id,
            expected_is_monitored=True,
            expected_mode="VERIFY",
            label="VERIFY 상태 보호",
        )

        _assert_single_focus(
            connection,
            region_codes,
            expected_cctv_id=(
                cctv_id
            ),
            expected_mode="VERIFY",
            label=(
                "VERIFY 중 추가 ALERT "
                "생성 금지"
            ),
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
                    status::text
                        AS status
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