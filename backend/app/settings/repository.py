"""
monitoring_settings와
개인 알림 설정 Repository.

트랜잭션은 Service에서 관리합니다.
"""


# ============================================================
# Monitoring Settings
# ============================================================


def get_monitoring_settings(
    connection,
    *,
    for_update: bool = False,
):
    """
    현재 OCTV 감시·분석 설정을 조회한다.

    monitoring_settings에 행이 여러 개라면
    가장 최근 id를 현재 설정으로 사용한다.
    """

    query = """
        SELECT
            id,
            base_analysis_interval_sec,
            alert_analysis_interval_sec,
            verify_analysis_interval_sec,
            candidate_confidence_threshold,
            candidate_min_detection_count,
            temporal_validation_sec,
            incident_confidence_threshold,
            reconnect_interval_sec,
            max_reconnect_attempts,
            quality_threshold,
            updated_by,
            updated_at
        FROM monitoring_settings
        ORDER BY id DESC
        LIMIT 1
    """

    if for_update:

        query += (
            " FOR UPDATE"
        )

    with connection.cursor() as cursor:

        cursor.execute(
            query
        )

        return (
            cursor.fetchone()
        )


def save_monitoring_settings(
    connection,
    settings_id: int,
    values: dict,
    updated_by: int,
):
    """
    기존 monitoring_settings 행을 수정한다.

    DB 구조는 변경하지 않는다.

    W06에서 관리하는 기존 10개 설정 컬럼을
    모두 저장한다.
    """

    fields = (
        "base_analysis_interval_sec",
        "alert_analysis_interval_sec",
        "verify_analysis_interval_sec",

        "candidate_confidence_threshold",
        "candidate_min_detection_count",
        "temporal_validation_sec",
        "incident_confidence_threshold",

        "reconnect_interval_sec",
        "max_reconnect_attempts",

        "quality_threshold",
    )

    assignments = ", ".join(
        f"{name} = %s"
        for name in fields
    )

    params = (
        tuple(
            values[
                name
            ]
            for name in fields
        )
        + (
            updated_by,
            settings_id,
        )
    )

    query = f"""
        UPDATE monitoring_settings
        SET
            {assignments},
            updated_by = %s,
            updated_at = (
                CURRENT_TIMESTAMP
                AT TIME ZONE 'UTC'
            )
        WHERE id = %s
        RETURNING id;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query,
            params,
        )

        return (
            cursor.fetchone()
        )


# ============================================================
# Personal Push Settings
# ============================================================


def set_notification_enabled(
    connection,
    user_id: int,
    enabled: bool,
):
    """
    활성 사용자의 개인 Push 수신 여부를 변경한다.
    """

    query = """
        UPDATE users
        SET notification_enabled = %s
        WHERE id = %s
          AND is_active = TRUE
        RETURNING notification_enabled;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (
                enabled,
                user_id,
            ),
        )

        return (
            cursor.fetchone()
        )