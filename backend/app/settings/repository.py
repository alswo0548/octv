"""Monitoring settings DB 조회/저장 Repository."""

from ..errors import FeatureNotImplemented


def get_monitoring_settings(connection):
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
        LIMIT 1;
    """

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

    현재는 API 구현 전 단계이므로
    실제 UPDATE 쿼리는 아직 구현하지 않는다.
    """

    # TODO:
    # 허용 필드만 갱신하고
    # updated_by·updated_at도 명시적으로 갱신.
    raise FeatureNotImplemented(
        "settings.save_monitoring_settings DB 쿼리 구현 예정"
    )


def set_notification_enabled(
    connection,
    user_id: int,
    enabled: bool,
):
    """
    사용자의 notification_enabled 설정을 수정한다.

    현재는 API 구현 전 단계이므로
    실제 UPDATE 쿼리는 아직 구현하지 않는다.
    """

    # TODO:
    # 본인 users.notification_enabled 값만 갱신.
    raise FeatureNotImplemented(
        "settings.set_notification_enabled DB 쿼리 구현 예정"
    )