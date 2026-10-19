"""W02 Dashboard 외부상황 PostgreSQL 통합 검사.

임시 지역 / CCTV / 사건 / 기상특보를 하나의 트랜잭션 안에서
생성하고 선택 사건 기준 외부상황 조회 결과를 확인한 뒤
항상 rollback합니다.

로컬 개발 DB와 CI의 빈 PostgreSQL 모두에서
같은 방식으로 실행할 수 있습니다.
"""

import sys
from contextlib import contextmanager
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo


ADMIN_USER = {
    "id": -1,
    "email": "dashboard-test@octv.local",
    "name": "Dashboard Test Admin",
    "role": "CONTROL_ADMIN",
    "agency_id": None,
    "notification_enabled": True,
    "is_active": True,
}


ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from backend.app.dashboard import (  # noqa: E402
    service,
)
from backend.app.db.session import (  # noqa: E402
    get_connection,
)


KST = ZoneInfo(
    "Asia/Seoul"
)


class _RollbackExternalStatusCheck(
    Exception
):
    """정상 검증 후 rollback을 발생시키기 위한 내부 예외."""


def _insert_test_region(
    connection,
    token: str,
) -> str:
    """
    CI의 빈 region 테이블에서도
    테스트가 독립적으로 실행되도록
    임시 지역을 생성한다.
    """

    region_code = (
        f"DASH-REG-{token}"
    )

    connection.execute(
        """
        INSERT INTO region (
            region_code,
            sido_name,
            sigungu_name,
            weather_region_code
        )
        VALUES (
            %s,
            '대시보드시',
            '외부상황구',
            NULL
        );
        """,
        (
            region_code,
        ),
    )

    return region_code


def _insert_test_cctv(
    connection,
    *,
    external_cctv_id: str,
    region_code: str,
) -> int:
    row = connection.execute(
        """
        INSERT INTO cctvs (
            external_cctv_id,
            name,
            provider,
            latitude,
            longitude,
            region_code,
            is_monitored,
            connection_status,
            monitored_mode
        )
        VALUES (
            %s,
            'Dashboard External Test CCTV',
            'DASHBOARD_TEST',
            37.5000000,
            127.0000000,
            %s,
            TRUE,
            'CONNECTED',
            'ALERT'
        )
        RETURNING id;
        """,
        (
            external_cctv_id,
            region_code,
        ),
    ).fetchone()

    return row["id"]


def _insert_test_incident(
    connection,
    *,
    cctv_id: int,
    token: str,
) -> int:
    """
    incidents 저장 정책에 맞춰
    UTC naive timestamp를 사용한다.
    """

    now_utc_naive = (
        datetime.now(
            timezone.utc
        )
        .replace(
            tzinfo=None
        )
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
            0.9500,
            'dashboard-external-check',
            '{}'::json,
            %s,
            'CONFIRMED',
            %s,
            %s
        )
        RETURNING id;
        """,
        (
            f"DASH-EXT-{token}",
            cctv_id,
            f"dashboard-ext-{token}",
            now_utc_naive,
            now_utc_naive,
        ),
    ).fetchone()

    return row["id"]


def _insert_test_weather_alert(
    connection,
    *,
    token: str,
    region_code: str,
) -> str:
    """
    weather_alerts Scheduler 저장 정책에 맞춰
    KST naive timestamp를 사용한다.
    """

    external_alert_id = (
        f"DASH-ALERT-{token}"
    )

    issued_at = (
        datetime.now(
            KST
        )
        .replace(
            tzinfo=None,
            microsecond=0,
        )
    )

    connection.execute(
        """
        INSERT INTO weather_alerts (
            external_alert_id,
            alert_type,
            alert_level,
            title,
            issued_at,
            ended_at,
            status,
            region_code
        )
        VALUES (
            %s,
            '호우',
            '주의보',
            '호우 주의보',
            %s,
            NULL,
            'ACTIVE',
            %s
        );
        """,
        (
            external_alert_id,
            issued_at,
            region_code,
        ),
    )

    return external_alert_id


def _check_external_status():
    token = uuid4().hex[:8]

    external_cctv_id = (
        f"DASH-EXT-CCTV-{token}"
    )

    try:
        with get_connection() as connection:

            # ---------------------------------------------
            # 테스트가 기존 DB 데이터에 의존하지 않도록
            # region부터 직접 생성한다.
            # ---------------------------------------------

            region_code = (
                _insert_test_region(
                    connection,
                    token,
                )
            )

            cctv_id = (
                _insert_test_cctv(
                    connection,
                    external_cctv_id=(
                        external_cctv_id
                    ),
                    region_code=(
                        region_code
                    ),
                )
            )

            incident_id = (
                _insert_test_incident(
                    connection,
                    cctv_id=cctv_id,
                    token=token,
                )
            )

            alert_id = (
                _insert_test_weather_alert(
                    connection,
                    token=token,
                    region_code=(
                        region_code
                    ),
                )
            )

            # ---------------------------------------------
            # service.get_external_status()가
            # 별도 connection을 열지 않고
            # 현재 rollback용 transaction을 사용하도록 한다.
            # ---------------------------------------------

            @contextmanager
            def same_connection():
                yield connection

            with patch.object(
                service,
                "get_connection",
                same_connection,
            ):
                result = (
                    service.get_external_status(
                        incident_id,
                        user=ADMIN_USER,
                    )
                )

            # ---------------------------------------------
            # 선택 사건 기준 정보
            # ---------------------------------------------

            assert (
                result.incident_id
                == incident_id
            )

            assert (
                result.cctv_id
                == cctv_id
            )

            assert (
                result.region_code
                == region_code
            )

            assert (
                result.region_name
                == "대시보드시 외부상황구"
            )

            # ---------------------------------------------
            # 기상특보
            # ---------------------------------------------

            assert (
                len(
                    result.weather_alerts
                )
                == 1
            )

            alert = (
                result.weather_alerts[0]
            )

            assert (
                alert.external_alert_id
                == alert_id
            )

            assert (
                alert.alert_type
                == "호우"
            )

            assert (
                alert.alert_level
                == "주의보"
            )

            assert (
                alert.title
                == "호우 주의보"
            )

            assert (
                alert.region_code
                == region_code
            )

            assert (
                alert.issued_at.utcoffset()
                == KST.utcoffset(
                    alert.issued_at
                )
            )

            # ---------------------------------------------
            # 집중감시 CCTV
            # ---------------------------------------------

            assert (
                result.focused_monitoring_cctv_count
                == 1
            )

            # ---------------------------------------------
            # 아직 API Key / MCP 미연결 항목
            # ---------------------------------------------

            assert (
                result.last_received_at
                is None
            )

            assert (
                result.rainfall_mm.value
                is None
            )

            assert (
                result.rainfall_mm.status
                == "NO_MAPPING"
            )

            assert (
                result.rainfall_mm.unit
                == "mm"
            )

            assert (
                result.water_level_m.value
                is None
            )

            assert (
                result.water_level_m.status
                == "NO_MAPPING"
            )

            assert (
                result.water_level_m.unit
                == "m"
            )

            assert (
                result.road_control_count.value
                is None
            )

            assert (
                result.road_control_count.status
                == "NO_MAPPING"
            )

            assert (
                result.road_control_count.unit
                == "count"
            )

            print(
                "PASS dashboard external "
                "status incident/weather/CCTV"
            )

            # 정상 성공이어도 commit하지 않고
            # transaction 전체를 rollback한다.
            raise (
                _RollbackExternalStatusCheck
            )

    except _RollbackExternalStatusCheck:
        pass

    # -----------------------------------------------------
    # rollback 확인
    # -----------------------------------------------------

    with get_connection() as connection:
        cctv_remaining = (
            connection.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM cctvs
                WHERE external_cctv_id = %s;
                """,
                (
                    external_cctv_id,
                ),
            )
            .fetchone()["n"]
        )

        region_remaining = (
            connection.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM region
                WHERE region_code = %s;
                """,
                (
                    f"DASH-REG-{token}",
                ),
            )
            .fetchone()["n"]
        )

    assert (
        cctv_remaining
        == 0
    )

    assert (
        region_remaining
        == 0
    )

    print(
        "PASS dashboard external "
        "status rollback"
    )


def main():
    _check_external_status()

    print(
        "\n"
        "DASHBOARD EXTERNAL STATUS "
        "CHECKS PASSED"
    )


if __name__ == "__main__":
    main()