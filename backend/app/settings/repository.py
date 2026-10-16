"""
감시 기준 DB 작업은 아직 미구현, 본인 Push 수신 설정만 갱신.

파일 흐름
1. 사용자 알림 ON/OFF 변경 요청에서는 users.notification_enabled만 UPDATE합니다.
2. 변경된 값을 반환하며 트랜잭션 확정은 Service에서 관리합니다.
"""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def get_monitoring_settings(connection):
    # TODO: monitoring_settings 조회. 활성 설정 행 선택/버전 정책은 팀과 합의.
    raise FeatureNotImplemented("settings.get_monitoring_settings DB 쿼리 구현 예정")


def save_monitoring_settings(
    connection, settings_id: int, values: dict, updated_by: int
):
    # TODO: 허용 필드만 갱신하고 updated_by·updated_at도 명시적으로 갱신.
    raise FeatureNotImplemented("settings.save_monitoring_settings DB 쿼리 구현 예정")


# 로그인한 사용자 본인의 Push ON/OFF 컬럼만 업데이트.
def set_notification_enabled(connection, user_id: int, enabled: bool):
    # user_id는 JWT에서 가져오며 비활성 계정의 설정은 변경하지 않습니다.
    return connection.execute(
        """
        UPDATE users
        SET notification_enabled = %s
        WHERE id = %s AND is_active = TRUE
        RETURNING notification_enabled
        """,
        (enabled, user_id),
    ).fetchone()
