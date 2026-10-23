"""Demo Scenario DB Repository."""


def get_cctv_by_external_id(
    connection,
    provider: str,
    external_cctv_id: str,
):
    """
    provider + external_cctv_id로
    Demo 대상 CCTV를 조회한다.
    """

    query = """
        SELECT
            id,
            external_cctv_id,
            name,
            provider,
            address,
            latitude,
            longitude,
            stream_url,
            is_monitored,
            connection_status,
            analysis_status,
            region_code,
            monitored_mode
        FROM cctvs
        WHERE provider = %s
          AND external_cctv_id = %s
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                provider,
                external_cctv_id,
            ),
        )

        return cursor.fetchone()


def get_demo_cctv_by_id(
    connection,
    cctv_id: int,
):
    """
    Demo 영상 재생에 필요한 CCTV 정보를 조회한다.
    """

    query = """
        SELECT
            id,
            external_cctv_id,
            name,
            provider,
            stream_url,
            is_monitored
        FROM cctvs
        WHERE id = %s
          AND provider = 'DEMO'
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (cctv_id,),
        )

        return cursor.fetchone()


def activate_demo_cctv(
    connection,
    *,
    provider: str,
    external_cctv_id: str,
    video: str,
):
    """
    Demo CCTV를 ALERT 감시 대상으로 활성화한다.

    connection_status / analysis_status는
    Runtime이 실제 동작하면서 갱신한다.
    """

    if provider.upper() != "DEMO":
        raise ValueError("Demo 활성화는 DEMO provider만 허용합니다.")

    query = """
        UPDATE cctvs
        SET
            stream_url = %s,
            is_monitored = TRUE,
            monitored_mode =
                'ALERT'
                ::monitored_mode_enum
        WHERE provider = %s
          AND external_cctv_id = %s
        RETURNING
            id,
            external_cctv_id,
            name,
            provider,
            region_code,
            stream_url,
            is_monitored,
            monitored_mode;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                video,
                provider,
                external_cctv_id,
            ),
        )

        return cursor.fetchone()


def deactivate_demo_cctv(
    connection,
    *,
    provider: str,
    external_cctv_id: str,
):
    """
    Demo CCTV를 감시 대상에서 제거한다.

    Runtime 상태값(connection_status 등)은
    직접 변경하지 않는다.
    """

    if provider.upper() != "DEMO":
        raise ValueError("Demo 종료는 DEMO provider만 허용합니다.")

    query = """
        UPDATE cctvs
        SET
            stream_url = NULL,
            is_monitored = FALSE,
            monitored_mode =
                'OFF'
                ::monitored_mode_enum
        WHERE provider = %s
          AND external_cctv_id = %s
          AND (
              is_monitored = TRUE
              OR stream_url IS NOT NULL
              OR monitored_mode <>
                  'OFF'
                  ::monitored_mode_enum
          )
        RETURNING
            id,
            external_cctv_id,
            name,
            provider,
            region_code,
            is_monitored,
            monitored_mode;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                provider,
                external_cctv_id,
            ),
        )

        return cursor.fetchone()


def upsert_demo_weather_alert(
    connection,
    *,
    external_alert_id: str,
    alert_type: str,
    alert_level: str,
    title: str,
    issued_at,
    region_code: str,
):
    query = """
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
            %s,
            %s,
            %s,
            %s,
            NULL,
            'ACTIVE'
                ::weather_status_enum,
            %s
        )
        ON CONFLICT (
            external_alert_id,
            region_code
        )
        DO UPDATE SET
            alert_type =
                EXCLUDED.alert_type,
            alert_level =
                EXCLUDED.alert_level,
            title =
                EXCLUDED.title,
            issued_at =
                EXCLUDED.issued_at,
            ended_at = NULL,
            status =
                'ACTIVE'
                ::weather_status_enum
        RETURNING
            external_alert_id,
            region_code,
            status;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                external_alert_id,
                alert_type,
                alert_level,
                title,
                issued_at,
                region_code,
            ),
        )

        return cursor.fetchone()


def count_active_demo_weather_alerts(
    connection,
    *,
    scenario_name: str,
) -> int:
    query = """
        SELECT COUNT(*) AS count
        FROM weather_alerts
        WHERE status =
              'ACTIVE'
              ::weather_status_enum
          AND external_alert_id
              LIKE %s;
    """

    pattern = f"DEMO:{scenario_name}:%"

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (pattern,),
        )

        row = cursor.fetchone()

    return int(row["count"])


def end_demo_weather_alerts(
    connection,
    *,
    scenario_name: str,
    ended_at,
) -> int:
    query = """
        UPDATE weather_alerts
        SET
            status =
                'ENDED'
                ::weather_status_enum,
            ended_at = %s
        WHERE status =
              'ACTIVE'
              ::weather_status_enum
          AND external_alert_id
              LIKE %s;
    """

    pattern = f"DEMO:{scenario_name}:%"

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                ended_at,
                pattern,
            ),
        )

        return cursor.rowcount
