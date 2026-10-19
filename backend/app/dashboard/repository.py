"""통합관제 Dashboard 조회 Repository."""

from datetime import datetime


def get_dashboard_summary(
    connection,
    today_start_utc: datetime,
    today_end_utc: datetime,
) -> dict:
    """
    W02 통합관제 상단 현황을 조회한다.

    - 감시 CCTV 수
    - 오늘 등록 사건 수
    - 연결 오류 수
    - 활성 기상특보 수

    사건은 DB에 UTC naive timestamp로 저장되므로,
    한국시간 기준 오늘의 시작/끝을
    UTC naive 값으로 변환해서 전달받는다.
    """

    query = """
        SELECT
            (
                SELECT COUNT(*)
                FROM cctvs
                WHERE is_monitored = TRUE
            )::int AS monitored_cctv_count,

            (
                SELECT COUNT(*)
                FROM incidents
                WHERE detected_at >= %s
                  AND detected_at < %s
                  AND status <> 'FALSE_POSITIVE'
            )::int AS today_incident_count,

            (
                SELECT COUNT(*)
                FROM cctvs
                WHERE is_monitored = TRUE
                  AND connection_status IN (
                      'DISCONNECTED',
                      'RECONNECTING'
                  )
            )::int AS connection_error_count,

            (
                SELECT COUNT(
                    DISTINCT external_alert_id
                )
                FROM weather_alerts
                WHERE status = 'ACTIVE'
            )::int AS active_weather_alert_count;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                today_start_utc,
                today_end_utc,
            ),
        )
        row = cursor.fetchone()

    return {
        "monitored_cctv_count":
            row["monitored_cctv_count"],

        "today_incident_count":
            row["today_incident_count"],

        "connection_error_count":
            row["connection_error_count"],

        "active_weather_alert_count":
            row["active_weather_alert_count"],
    }


DASHBOARD_INCIDENT_FROM_SQL = """
    FROM incidents AS i

    JOIN cctvs AS c
      ON c.id = i.cctv_id

    LEFT JOIN region AS r
      ON r.region_code = c.region_code

    LEFT JOIN LATERAL (
        SELECT
            ia.priority
        FROM incident_assessments AS ia
        WHERE ia.incident_id = i.id
        ORDER BY ia.id DESC
        LIMIT 1
    ) AS assessment
      ON TRUE

    WHERE i.status IN (
        'DETECTED',
        'CONFIRMED',
        'SENT'
    )
      AND assessment.priority IN (
        'P1',
        'P2'
    )
"""


def count_dashboard_incidents(
    connection,
) -> int:
    """
    W02 긴급 사건 전체 건수를 조회한다.

    현재 진행 중인 P1/P2 사건만 대상이다.
    """

    query = (
        """
        SELECT COUNT(*)::int AS total
        """
        + DASHBOARD_INCIDENT_FROM_SQL
        + ";"
    )

    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()

    return row["total"]


def list_dashboard_incidents(
    connection,
    page: int = 1,
    page_size: int = 5,
) -> list[dict]:
    """
    W02 통합관제 화면에 표시할 사건을 조회한다.

    - 현재 진행 중인 사건만 조회
      DETECTED / CONFIRMED / SENT
    - P1 → P2 순
    - 같은 우선순위에서는 최근 탐지 사건 우선
    - 한 페이지 기본 5건
    - 목록과 지도에서 동일한 사건 배열 사용
    """

    offset = (
        page - 1
    ) * page_size

    query = (
        """
        SELECT
            i.id,
            i.incident_no,
            i.hazard_type,
            i.status,

            assessment.priority,

            c.id AS cctv_id,
            c.name AS cctv_name,

            CONCAT_WS(
                ' ',
                r.sido_name,
                r.sigungu_name
            ) AS region_name,

            c.latitude,
            c.longitude,

            i.detected_at
        """
        + DASHBOARD_INCIDENT_FROM_SQL
        + """
        ORDER BY
            CASE assessment.priority
                WHEN 'P1' THEN 1
                WHEN 'P2' THEN 2
                ELSE 3
            END,
            i.detected_at DESC,
            i.id DESC

        LIMIT %s
        OFFSET %s;
        """
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                page_size,
                offset,
            ),
        )
        rows = cursor.fetchall()

    return [
        {
            "id":
                row["id"],

            "incident_no":
                row["incident_no"],

            "hazard_type":
                row["hazard_type"],

            "status":
                row["status"],

            "priority":
                row["priority"],

            "cctv_id":
                row["cctv_id"],

            "cctv_name":
                row["cctv_name"],

            "region_name":
                row["region_name"],

            "latitude": (
                float(
                    row["latitude"]
                )
                if row["latitude"] is not None
                else None
            ),

            "longitude": (
                float(
                    row["longitude"]
                )
                if row["longitude"] is not None
                else None
            ),

            "detected_at":
                row["detected_at"],
        }

        for row in rows
    ]


def get_external_status_incident(
    connection,
    incident_id: int,
) -> dict | None:
    """
    외부상황 패널의 기준이 될 사건을 조회한다.

    Dashboard 목록에서 선택한 incident_id를 기준으로
    CCTV와 지역 정보를 가져온다.
    """

    query = """
        SELECT
            i.id,
            i.incident_no,
            i.cctv_id,

            c.name AS cctv_name,
            c.region_code,
            c.latitude,
            c.longitude,

            CONCAT_WS(
                ' ',
                r.sido_name,
                r.sigungu_name
            ) AS region_name

        FROM incidents AS i

        JOIN cctvs AS c
          ON c.id = i.cctv_id

        LEFT JOIN region AS r
          ON r.region_code = c.region_code

        WHERE i.id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                incident_id,
            ),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return {
        "id":
            row["id"],

        "incident_no":
            row["incident_no"],

        "cctv_id":
            row["cctv_id"],

        "cctv_name":
            row["cctv_name"],

        "region_code":
            row["region_code"],

        "region_name":
            row["region_name"],

        "latitude": (
            float(
                row["latitude"]
            )
            if row["latitude"] is not None
            else None
        ),

        "longitude": (
            float(
                row["longitude"]
            )
            if row["longitude"] is not None
            else None
        ),
    }


def list_active_weather_alerts(
    connection,
    region_code: str | None,
) -> list[dict]:
    """
    선택한 사건의 지역에 현재 활성화된
    기상특보를 조회한다.

    weather_alerts.issued_at은
    현재 기상특보 Scheduler 정책상 KST naive이다.
    """

    if not region_code:
        return []

    query = """
        SELECT
            external_alert_id,
            alert_type,
            alert_level,
            title,
            issued_at,
            region_code

        FROM weather_alerts

        WHERE region_code = %s
          AND status = 'ACTIVE'

        ORDER BY
            CASE alert_level
                WHEN '경보' THEN 1
                WHEN '주의보' THEN 2
                WHEN '예비특보' THEN 3
                ELSE 4
            END,
            issued_at DESC,
            external_alert_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                region_code,
            ),
        )
        rows = cursor.fetchall()

    return [
        {
            "external_alert_id":
                row["external_alert_id"],

            "alert_type":
                row["alert_type"],

            "alert_level":
                row["alert_level"],

            "title":
                row["title"],

            "issued_at":
                row["issued_at"],

            "region_code":
                row["region_code"],
        }

        for row in rows
    ]


def count_focused_monitoring_cctvs(
    connection,
    region_code: str | None,
) -> int:
    """
    선택한 사건 지역에서 현재 ALERT 모드로
    집중감시 중인 CCTV 수를 반환한다.
    """

    if not region_code:
        return 0

    query = """
        SELECT
            COUNT(*)::int AS total

        FROM cctvs

        WHERE region_code = %s
          AND is_monitored = TRUE
          AND monitored_mode = 'ALERT';
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                region_code,
            ),
        )
        row = cursor.fetchone()

    return row["total"]