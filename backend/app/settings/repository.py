"""최신 monitoring_settings 행과 개인 알림 설정을 조회·갱신합니다. 트랜잭션은 Service가 관리합니다."""


def get_monitoring_settings(connection, *, for_update=False):
    """
    현재 OCTV 감시·분석 설정을 조회한다.

    monitoring_settings에 데이터가 없으면
    None을 반환한다.

    현재 테이블에는 active/version 컬럼이 없으므로,
    여러 행이 존재할 경우 가장 최근 id의 설정을 사용한다.
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
        query += " FOR UPDATE"

    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()

    return row


def save_monitoring_settings(
    connection,
    settings_id: int,
    values: dict,
    updated_by: int,
):
    """
    monitoring_settings를 수정한다.

    허용된 필드만 수정하고 UTC 수정 시각을 기록한다.
    """

    # 허용 필드만 갱신하고 updated_by·updated_at도 명시적으로 갱신.
    fields = (
        "base_analysis_interval_sec", "alert_analysis_interval_sec",
        "verify_analysis_interval_sec", "reconnect_interval_sec",
        "max_reconnect_attempts", "quality_threshold",
    )
    assignments = ", ".join(f"{name} = %s" for name in fields)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE monitoring_settings SET {assignments}, updated_by = %s, "
            "updated_at = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') "
            "WHERE id = %s RETURNING id",
            tuple(values[name] for name in fields) + (updated_by, settings_id),
        )
        return cursor.fetchone()


def set_notification_enabled(
    connection,
    user_id: int,
    enabled: bool,
):
    """
    로그인한 사용자 본인의
    Push 알림 ON/OFF 설정을 변경한다.

    비활성 사용자의 설정은 변경하지 않는다.
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

        row = cursor.fetchone()

    return row
