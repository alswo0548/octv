"""W02 Dashboard PostgreSQL integration checks.

테스트용 CCTV / 사건 / 평가 데이터를 하나의 트랜잭션 안에서 생성하고
Dashboard 조회 결과를 검증한 뒤 항상 rollback합니다.

실제 개발 DB에는 테스트 데이터가 남지 않습니다.
"""

import sys
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


# ------------------------------------------------------------
# python tests/run_dashboard_checks.py 로 직접 실행해도
# 프로젝트 루트의 backend 패키지를 import할 수 있게 합니다.
# ------------------------------------------------------------

ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from backend.app.dashboard import (  # noqa: E402
    repository,
    service,
)
from backend.app.db.session import (  # noqa: E402
    get_connection,
)


KST = ZoneInfo(
    "Asia/Seoul"
)


class _RollbackDashboardCheck(
    Exception
):
    """정상 검증 후 rollback을 발생시키기 위한 내부 예외."""


def _insert_test_cctv(
    connection,
    external_cctv_id: str,
) -> int:
    row = connection.execute(
        """
        INSERT INTO cctvs (
            external_cctv_id,
            name,
            provider,
            latitude,
            longitude,
            is_monitored,
            connection_status,
            monitored_mode
        )
        VALUES (
            %s,
            'Dashboard Test CCTV',
            'DASHBOARD_TEST',
            37.5000000,
            127.0000000,
            TRUE,
            'CONNECTED',
            'BASE'
        )
        RETURNING id;
        """,
        (
            external_cctv_id,
        ),
    ).fetchone()

    return row["id"]


def _insert_test_incident(
    connection,
    *,
    cctv_id: int,
    suffix: str,
    detected_at: datetime,
    priority: str,
    priority_score: float,
) -> int:
    incident_no = (
        "OCTV-DASHBOARD-"
        + suffix
    )

    dedup_key = (
        "dashboard-check-"
        + suffix
    )

    row = connection.execute(
        """
        INSERT INTO incidents (
            incident_no,
            cctv_id,
            hazard_type,
            confidence,
            model_version,
            detection_bbox_json,
            dedup_key,
            status,
            detected_at,
            last_detected_at
        )
        VALUES (
            %s,
            %s,
            'flood',
            0.9000,
            'dashboard-check',
            '{}'::json,
            %s,
            'CONFIRMED',
            %s,
            %s
        )
        RETURNING id;
        """,
        (
            incident_no,
            cctv_id,
            dedup_key,
            detected_at,
            detected_at,
        ),
    ).fetchone()

    incident_id = row["id"]

    connection.execute(
        """
        INSERT INTO incident_assessments (
            incident_id,
            risk_score,
            risk_level,
            risk_breakdown_json,
            priority_score,
            priority,
            priority_breakdown_json,
            rule_version
        )
        VALUES (
            %s,
            90.00,
            'HIGH',
            '{}'::json,
            %s,
            %s,
            '{}'::json,
            'dashboard-check'
        );
        """,
        (
            incident_id,
            priority_score,
            priority,
        ),
    )

    return incident_id


def _check_time_conversion():
    """
    UTC naive 사건 시각이
    Dashboard에서 KST로 정확히 변환되는지 확인.
    """

    utc_naive = datetime(
        2026,
        10,
        19,
        1,
        30,
        0,
    )

    converted = (
        service._utc_naive_to_kst(
            utc_naive
        )
    )

    assert (
        converted.year,
        converted.month,
        converted.day,
        converted.hour,
        converted.minute,
    ) == (
        2026,
        10,
        19,
        10,
        30,
    )

    assert (
        converted.utcoffset()
        == timedelta(
            hours=9
        )
    )

    print(
        "PASS dashboard UTC -> KST conversion"
    )


def _check_today_range():
    """
    한국시간 오늘 범위를
    UTC naive 범위로 변환했을 때
    정확히 24시간이며 KST 자정에 대응하는지 확인.
    """

    start_utc, end_utc = (
        service._today_utc_range()
    )

    assert (
        start_utc.tzinfo is None
    )

    assert (
        end_utc.tzinfo is None
    )

    assert (
        end_utc
        - start_utc
        == timedelta(
            days=1
        )
    )

    start_kst = (
        start_utc
        .replace(
            tzinfo=timezone.utc
        )
        .astimezone(
            KST
        )
    )

    end_kst = (
        end_utc
        .replace(
            tzinfo=timezone.utc
        )
        .astimezone(
            KST
        )
    )

    assert (
        start_kst.hour,
        start_kst.minute,
        start_kst.second,
    ) == (
        0,
        0,
        0,
    )

    assert (
        end_kst.hour,
        end_kst.minute,
        end_kst.second,
    ) == (
        0,
        0,
        0,
    )

    print(
        "PASS dashboard KST today range"
    )


def _check_postgres():
    """
    임시 CCTV 1대와 사건 7건을 만든다.

    P1 6건:
        페이지네이션 검증

    P2 1건:
        P2가 더 최신이어도
        P1 뒤에 정렬되는지 검증

    모든 데이터는 마지막에 rollback한다.
    """

    token = uuid4().hex[:8]

    external_cctv_id = (
        "DASHBOARD-CHECK-"
        + token
    )

    p1_ids = []
    p2_id = None

    try:
        with get_connection() as connection:

            cctv_id = (
                _insert_test_cctv(
                    connection,
                    external_cctv_id,
                )
            )

            # 기존 실제 사건보다 확실히 뒤에 정렬되도록
            # 테스트 전용 미래 시각을 사용합니다.
            base_time = datetime(
                2099,
                1,
                1,
                0,
                0,
                0,
            )

            # -------------------------------------------------
            # P1 사건 6건
            # -------------------------------------------------

            for index in range(6):
                incident_id = (
                    _insert_test_incident(
                        connection,
                        cctv_id=cctv_id,
                        suffix=(
                            token
                            + "-P1-"
                            + str(index)
                        ),
                        detected_at=(
                            base_time
                            + timedelta(
                                minutes=index
                            )
                        ),
                        priority="P1",
                        priority_score=(
                            90.0
                            + index
                        ),
                    )
                )

                p1_ids.append(
                    incident_id
                )

            # -------------------------------------------------
            # P2 사건 1건
            #
            # P1보다 시간은 더 최신으로 만들지만,
            # priority 정렬 때문에 P1 뒤에 있어야 합니다.
            # -------------------------------------------------

            p2_id = (
                _insert_test_incident(
                    connection,
                    cctv_id=cctv_id,
                    suffix=(
                        token
                        + "-P2"
                    ),
                    detected_at=datetime(
                        2100,
                        1,
                        1,
                        0,
                        0,
                        0,
                    ),
                    priority="P2",
                    priority_score=80.0,
                )
            )

            # -------------------------------------------------
            # 전체 건수
            # -------------------------------------------------

            total = (
                repository.count_dashboard_incidents(
                    connection
                )
            )

            assert total >= 7

            # -------------------------------------------------
            # PAGE 1
            # -------------------------------------------------

            page1 = (
                repository.list_dashboard_incidents(
                    connection,
                    page=1,
                    page_size=5,
                )
            )

            assert len(
                page1
            ) == 5

            expected_page1_ids = list(
                reversed(
                    p1_ids[1:]
                )
            )

            actual_page1_ids = [
                item["id"]
                for item in page1
            ]

            assert (
                actual_page1_ids
                == expected_page1_ids
            ), (
                "PAGE 1 ordering mismatch\n"
                f"expected={expected_page1_ids}\n"
                f"actual={actual_page1_ids}"
            )

            # 지도에 그대로 사용할 좌표 확인
            for item in page1:
                assert (
                    item["latitude"]
                    == 37.5
                )

                assert (
                    item["longitude"]
                    == 127.0
                )

                assert (
                    item["priority"]
                    == "P1"
                )

            # -------------------------------------------------
            # PAGE 2
            # -------------------------------------------------

            page2 = (
                repository.list_dashboard_incidents(
                    connection,
                    page=2,
                    page_size=5,
                )
            )

            assert page2

            assert (
                page2[0]["id"]
                == p1_ids[0]
            ), (
                "PAGE 2 first incident mismatch"
            )

            # -------------------------------------------------
            # P1 / P2 우선순위 정렬
            # -------------------------------------------------

            ordered = (
                repository.list_dashboard_incidents(
                    connection,
                    page=1,
                    page_size=20,
                )
            )

            ordered_ids = [
                item["id"]
                for item in ordered
            ]

            p2_position = (
                ordered_ids.index(
                    p2_id
                )
            )

            for p1_id in p1_ids:
                assert (
                    ordered_ids.index(
                        p1_id
                    )
                    < p2_position
                )

            print(
                "PASS dashboard PostgreSQL "
                "pagination/order/coordinates"
            )

            # 정상 성공이어도 commit하지 않고 rollback.
            raise _RollbackDashboardCheck

    except _RollbackDashboardCheck:
        pass

    # ---------------------------------------------------------
    # 실제 rollback 여부 확인
    # ---------------------------------------------------------

    with get_connection() as connection:
        remaining = (
            connection.execute(
                """
                SELECT COUNT(*)::int
                    AS n
                FROM cctvs
                WHERE external_cctv_id = %s;
                """,
                (
                    external_cctv_id,
                ),
            )
            .fetchone()["n"]
        )

    assert (
        remaining == 0
    ), (
        "Dashboard 테스트 데이터가 "
        "rollback되지 않았습니다."
    )

    print(
        "PASS dashboard rollback"
    )


def main():
    _check_time_conversion()
    _check_today_range()
    _check_postgres()

    print(
        "\n"
        "DASHBOARD CHECKS PASSED"
    )


if __name__ == "__main__":
    main()