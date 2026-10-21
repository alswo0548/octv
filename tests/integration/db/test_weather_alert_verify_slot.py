"""Weather Scheduler VERIFY 집중감시 슬롯 회귀 테스트.

재현하려는 문제:

1. 기상특보로 CCTV A가 ALERT
2. Incident 후보 검증 때문에 A가 VERIFY
3. Weather Scheduler가 ALERT가 없다고 오판
4. CCTV B를 새 ALERT로 추가
5. 반복되면 ALERT / VERIFY CCTV가 계속 증가

수정 후 기대 동작:

- 활성 특보 지역에 ALERT 또는 VERIFY가 하나라도 있으면
  해당 지역의 집중감시 슬롯은 이미 사용 중으로 본다.
- 따라서 Scheduler는 새로운 ALERT CCTV를 추가하지 않는다.

모든 DB 변경은 마지막에 ROLLBACK한다.
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


def _select_test_region(
    connection,
) -> dict:
    """
    weather_region_code가 있고
    UTIC CCTV가 2대 이상 존재하는 지역을 선택한다.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                r.region_code,
                r.weather_region_code
            FROM region AS r
            JOIN cctvs AS c
              ON c.region_code = r.region_code
            WHERE r.weather_region_code IS NOT NULL
              AND cardinality(
                  r.weather_region_code
              ) > 0
              AND c.provider = 'UTIC'
              AND c.external_cctv_id IS NOT NULL
            GROUP BY
                r.region_code,
                r.weather_region_code
            HAVING COUNT(c.id) >= 2
            ORDER BY r.region_code
            LIMIT 1;
            """
        )

        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "VERIFY 슬롯 테스트가 가능한 "
            "UTIC CCTV 2대 이상 지역이 없습니다."
        )

    return row


def _list_region_cctvs(
    connection,
    region_code: str,
) -> list[dict]:
    """
    테스트 지역의 UTIC CCTV 상태 조회.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                name,
                is_monitored,
                monitored_mode::text
                    AS monitored_mode
            FROM cctvs
            WHERE region_code = %s
              AND provider = 'UTIC'
              AND external_cctv_id IS NOT NULL
            ORDER BY id;
            """,
            (
                region_code,
            ),
        )

        return cursor.fetchall()


def _build_snow_warning(
    weather_region_code: str,
) -> KmaWarningStatus:
    """
    테스트용 대설주의보.
    """

    issued_at = datetime(
        2099,
        1,
        1,
        12,
        0,
    )

    return KmaWarningStatus(
        weather_region_code=(
            weather_region_code
        ),
        region_name=(
            "OCTV_VERIFY_SLOT_TEST"
        ),
        issued_at=(
            issued_at
        ),
        effective_at=(
            issued_at
        ),
        warning_code="S",
        warning_name="대설",
        level_code="2",
        level_name="주의보",
        command_code="1",
        command_name="발표",
        active=True,
    )


def main() -> None:
    print("=" * 72)

    print(
        "WEATHER ALERT VERIFY SLOT "
        "POSTGRESQL REGRESSION TEST"
    )

    print("=" * 72)

    connection = psycopg.connect(
        **database_connect_kwargs(),
        row_factory=dict_row,
    )

    try:
        target = _select_test_region(
            connection
        )

        region_code = str(
            target[
                "region_code"
            ]
        )

        weather_region_code = str(
            target[
                "weather_region_code"
            ][0]
        )

        rows = _list_region_cctvs(
            connection,
            region_code,
        )

        if len(rows) < 2:
            raise AssertionError(
                "테스트 지역에 CCTV가 "
                "2대 이상 있어야 합니다."
            )

        verify_cctv_id = int(
            rows[0]["id"]
        )

        other_cctv_ids = [
            int(row["id"])
            for row
            in rows[1:]
        ]

        print(
            "region:",
            region_code,
        )

        print(
            "weather code:",
            weather_region_code,
        )

        print(
            "VERIFY CCTV:",
            verify_cctv_id,
        )

        # ----------------------------------------------------
        # 기존 weather_alerts는 테스트 transaction 안에서 제거.
        # 최종 rollback으로 복구된다.
        # ----------------------------------------------------

        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM weather_alerts;
                """
            )

        # ----------------------------------------------------
        # 테스트 지역의 UTIC CCTV를 모두 OFF로 초기화한 뒤
        # 한 대만 VERIFY로 만든다.
        #
        # 이 상태에서 Scheduler가 다른 CCTV를
        # ALERT로 올리면 기존 버그가 재현된 것이다.
        # ----------------------------------------------------

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cctvs
                SET
                    is_monitored = FALSE,
                    monitored_mode =
                        'OFF'
                        ::monitored_mode_enum
                WHERE region_code = %s
                  AND provider = 'UTIC'
                  AND external_cctv_id IS NOT NULL;
                """,
                (
                    region_code,
                ),
            )

            cursor.execute(
                """
                UPDATE cctvs
                SET
                    is_monitored = TRUE,
                    monitored_mode =
                        'VERIFY'
                        ::monitored_mode_enum
                WHERE id = %s;
                """,
                (
                    verify_cctv_id,
                ),
            )

        before_rows = _list_region_cctvs(
            connection,
            region_code,
        )

        print(
            "[BEFORE]"
        )

        for row in before_rows:
            print(row)

        warning = (
            _build_snow_warning(
                weather_region_code
            )
        )

        result = (
            synchronize_weather_alerts(
                connection,
                [
                    warning,
                ],
            )
        )

        if (
            result[
                "cctv_to_alert_count"
            ]
            != 0
        ):
            raise AssertionError(
                "VERIFY CCTV가 이미 존재하는데 "
                "새 ALERT CCTV가 생성되었습니다. "
                f"cctv_to_alert_count="
                f"{result['cctv_to_alert_count']}"
            )

        after_rows = _list_region_cctvs(
            connection,
            region_code,
        )

        print(
            "[AFTER]"
        )

        for row in after_rows:
            print(row)

        verify_row = next(
            (
                row
                for row in after_rows
                if int(row["id"])
                == verify_cctv_id
            ),
            None,
        )

        if verify_row is None:
            raise AssertionError(
                "VERIFY CCTV를 찾을 수 없습니다."
            )

        if (
            not bool(
                verify_row[
                    "is_monitored"
                ]
            )
            or
            str(
                verify_row[
                    "monitored_mode"
                ]
            )
            != "VERIFY"
        ):
            raise AssertionError(
                "기존 VERIFY CCTV 상태가 "
                "변경되었습니다."
            )

        unexpected_alerts = [
            row
            for row in after_rows
            if (
                int(row["id"])
                in other_cctv_ids
                and str(
                    row[
                        "monitored_mode"
                    ]
                )
                == "ALERT"
            )
        ]

        if unexpected_alerts:
            raise AssertionError(
                "VERIFY 슬롯이 있는데 "
                "추가 ALERT CCTV가 생겼습니다: "
                f"{unexpected_alerts}"
            )

        print()
        print(
            "[PASS] VERIFY 상태를 "
            "집중감시 슬롯으로 인식"
        )

        print(
            "[PASS] 추가 ALERT CCTV 생성 차단"
        )

        print(
            "[SUCCESS] "
            "Weather Alert VERIFY Slot "
            "회귀 테스트 정상"
        )

    finally:
        connection.rollback()
        connection.close()

        print(
            "[ROLLBACK] "
            "DB 테스트 변경사항 원상복구 완료"
        )


if __name__ == "__main__":
    main()