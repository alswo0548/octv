"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

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


def set_notification_enabled(connection, user_id: int, enabled: bool):
    # TODO: 본인 users.notification_enabled 값만 갱신.
    raise FeatureNotImplemented("settings.set_notification_enabled DB 쿼리 구현 예정")
