"""통합관제 Dashboard 조회 Repository."""

from datetime import datetime


def _agency_access_clause(
    *,
    incident_alias: str,
    agency_id: int | None,
    agency_scoped: bool,
) -> tuple[str, list]:
    """로그인 기관 기준 사건 접근 SQL 조건을 만든다."""

    if not agency_scoped:
        return (
            "TRUE",
            [],
        )

    if agency_id is None:
        return (
            "FALSE",
            [],
        )

    return (
        f"""
        EXISTS (
            SELECT 1
            FROM incident_agency_recommendations AS ar
            WHERE ar.incident_id = {incident_alias}.id
              AND ar.agency_id = %s
              AND ar.recommendation_status
                  IN ('DELIVERED', 'COMPLETED')
        )
        """,
        [agency_id],
    )


def get_dashboard_summary(
    connection,
    today_start_utc: datetime,
    today_end_utc: datetime,
    *,
    agency_id: int | None = None,
    agency_scoped: bool = False,
) -> dict:
    """
    W02 통합관제 상단 현황을 조회한다.

    CONTROL_ADMIN:
    - 전체 감시 CCTV
    - 전체 오늘 사건
    - 전체 연결 오류
    - 전체 활성 기상특보

    AGENCY_STAFF / RESPONDER:
    - 소속 기관에 DELIVERED / COMPLETED된 사건 범위만 사용
    - 현재 진행 중인 접근 가능 사건과 연결된 CCTV/특보만 집계

    사건은 DB에 UTC naive timestamp로 저장되므로,
    한국시간 기준 오늘의 시작/끝을 UTC naive 값으로 전달받는다.
    """

    if not agency_scoped:
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

        params = (
            today_start_utc,
            today_end_utc,
        )

    else:
        if agency_id is None:
            return {
                "monitored_cctv_count": 0,
                "today_incident_count": 0,
                "connection_error_count": 0,
                "active_weather_alert_count": 0,
            }

        query = """
            WITH accessible_incidents AS (
                SELECT
                    i.id,
                    i.cctv_id,
                    i.detected_at,
                    i.status
                FROM incidents AS i
                WHERE i.status <> 'FALSE_POSITIVE'
                  AND EXISTS (
                      SELECT 1
                      FROM incident_agency_recommendations AS ar
                      WHERE ar.incident_id = i.id
                        AND ar.agency_id = %s
                        AND ar.recommendation_status
                            IN ('DELIVERED', 'COMPLETED')
                  )
            ),
            active_accessible_incidents AS (
                SELECT *
                FROM accessible_incidents
                WHERE status IN (
                    'DETECTED',
                    'CONFIRMED',
                    'SENT'
                )
            ),
            active_accessible_cctvs AS (
                SELECT DISTINCT
                    c.id,
                    c.region_code,
                    c.is_monitored,
                    c.connection_status
                FROM cctvs AS c
                JOIN active_accessible_incidents AS ai
                  ON ai.cctv_id = c.id
            )
            SELECT
                (
                    SELECT COUNT(*)
                    FROM active_accessible_cctvs
                    WHERE is_monitored = TRUE
                )::int AS monitored_cctv_count,

                (
                    SELECT COUNT(*)
                    FROM accessible_incidents
                    WHERE detected_at >= %s
                      AND detected_at < %s
                )::int AS today_incident_count,

                (
                    SELECT COUNT(*)
                    FROM active_accessible_cctvs
                    WHERE is_monitored = TRUE
                      AND connection_status IN (
                          'DISCONNECTED',
                          'RECONNECTING'
                      )
                )::int AS connection_error_count,

                (
                    SELECT COUNT(
                        DISTINCT wa.external_alert_id
                    )
                    FROM weather_alerts AS wa
                    WHERE wa.status = 'ACTIVE'
                      AND EXISTS (
                          SELECT 1
                          FROM active_accessible_cctvs AS c
                          WHERE c.region_code = wa.region_code
                      )
                )::int AS active_weather_alert_count;
        """

        params = (
            agency_id,
            today_start_utc,
            today_end_utc,
        )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            params,
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
    *,
    agency_id: int | None = None,
    agency_scoped: bool = False,
) -> int:
    """
    W02 긴급 사건 전체 건수를 조회한다.

    관리자는 전체 진행 중 P1/P2 사건,
    기관/현장 사용자는 소속 기관에 전달된 사건만 조회한다.
    """

    access_sql, access_params = (
        _agency_access_clause(
            incident_alias="i",
            agency_id=agency_id,
            agency_scoped=agency_scoped,
        )
    )

    query = (
        """
        SELECT COUNT(*)::int AS total
        """
        + DASHBOARD_INCIDENT_FROM_SQL
        + " AND ("
        + access_sql
        + ");"
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            access_params,
        )
        row = cursor.fetchone()

    return row["total"]


def list_dashboard_incidents(
    connection,
    page: int = 1,
    page_size: int = 5,
    *,
    agency_id: int | None = None,
    agency_scoped: bool = False,
) -> list[dict]:
    """
    W02 통합관제 화면에 표시할 사건을 조회한다.

    - 현재 진행 중인 사건만 조회
      DETECTED / CONFIRMED / SENT
    - P1 → P2 순
    - 같은 우선순위에서는 최근 탐지 사건 우선
    - 기관/현장 사용자는 소속기관에 전달된 사건만 조회
    - 한 페이지 기본 5건
    - 목록과 지도에서 동일한 사건 배열 사용
    """

    offset = (
        page - 1
    ) * page_size

    access_sql, access_params = (
        _agency_access_clause(
            incident_alias="i",
            agency_id=agency_id,
            agency_scoped=agency_scoped,
        )
    )

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
        + " AND ("
        + access_sql
        + ")"
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
            [
                *access_params,
                page_size,
                offset,
            ],
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
    *,
    agency_id: int | None = None,
    agency_scoped: bool = False,
) -> dict | None:
    """
    외부상황 패널의 기준이 될 사건을 조회한다.

    기관/현장 사용자는 자기 기관에
    DELIVERED / COMPLETED된 사건만 조회할 수 있다.
    """

    access_sql, access_params = (
        _agency_access_clause(
            incident_alias="i",
            agency_id=agency_id,
            agency_scoped=agency_scoped,
        )
    )

    query = (
        """
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

        WHERE i.id = %s
          AND (
        """
        + access_sql
        + """
          );
        """
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            [
                incident_id,
                *access_params,
            ],
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


def list_overview_weather_alerts(
    connection,
    *,
    agency_id: int | None = None,
    agency_scoped: bool = False,
) -> list[dict]:
    """
    W02에서 사건을 선택하지 않았을 때 표시할
    현재 관제 범위의 활성 기상특보를 조회한다.

    CONTROL_ADMIN:
    - 현재 감시 중인 CCTV 지역의 활성 특보

    AGENCY_STAFF / RESPONDER:
    - 자기 기관에 전달된 진행 사건과 연결된
      감시 CCTV 지역의 활성 특보
    """

    if (
        agency_scoped
        and agency_id is None
    ):
        return []

    scope_sql = """
        EXISTS (
            SELECT 1
            FROM cctvs AS c
            WHERE c.region_code = wa.region_code
              AND c.is_monitored = TRUE
        )
    """

    params = []

    if agency_scoped:
        scope_sql = """
            EXISTS (
                SELECT 1
                FROM incidents AS i

                JOIN cctvs AS c
                  ON c.id = i.cctv_id

                JOIN incident_agency_recommendations AS ar
                  ON ar.incident_id = i.id

                WHERE c.region_code = wa.region_code
                  AND c.is_monitored = TRUE
                  AND i.status IN (
                      'DETECTED',
                      'CONFIRMED',
                      'SENT'
                  )
                  AND ar.agency_id = %s
                  AND ar.recommendation_status
                      IN ('DELIVERED', 'COMPLETED')
            )
        """

        params.append(
            agency_id
        )

    query = (
        """
        SELECT
            wa.external_alert_id,
            wa.alert_type,
            wa.alert_level,
            wa.title,
            wa.issued_at,
            wa.region_code

        FROM weather_alerts AS wa

        WHERE wa.status = 'ACTIVE'
          AND (
        """
        + scope_sql
        + """
          )

        ORDER BY
            CASE wa.alert_level
                WHEN '경보' THEN 1
                WHEN '주의보' THEN 2
                WHEN '예비특보' THEN 3
                ELSE 4
            END,
            wa.issued_at DESC,
            wa.external_alert_id,
            wa.region_code;
        """
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            params,
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


def count_overview_focused_monitoring_cctvs(
    connection,
    *,
    agency_id: int | None = None,
    agency_scoped: bool = False,
) -> int:
    """
    W02 전체 상황에 표시할
    현재 ALERT 모드 집중감시 CCTV 수를 반환한다.
    """

    if (
        agency_scoped
        and agency_id is None
    ):
        return 0

    scope_sql = "TRUE"
    params = []

    if agency_scoped:
        scope_sql = """
            EXISTS (
                SELECT 1
                FROM incidents AS i

                JOIN incident_agency_recommendations AS ar
                  ON ar.incident_id = i.id

                WHERE i.cctv_id = c.id
                  AND i.status IN (
                      'DETECTED',
                      'CONFIRMED',
                      'SENT'
                  )
                  AND ar.agency_id = %s
                  AND ar.recommendation_status
                      IN ('DELIVERED', 'COMPLETED')
            )
        """

        params.append(
            agency_id
        )

    query = (
        """
        SELECT
            COUNT(*)::int AS total

        FROM cctvs AS c

        WHERE c.is_monitored = TRUE
          AND c.monitored_mode = 'ALERT'
          AND (
        """
        + scope_sql
        + """
          );
        """
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            params,
        )

        row = cursor.fetchone()

    return row["total"]


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