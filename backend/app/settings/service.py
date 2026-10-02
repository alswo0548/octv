"""
감시 기준·개인 알림 설정: 관리자 감시 기준과 개인 알림 수신 설정을 분리하세요. 감시 기준은
backend/app/settings/sql/monitoring_settings.sql의 필드와 단위를 맞추세요.
"""

from ..errors import FeatureNotImplemented
from . import schemas


def get_monitoring_settings():
    # TODO: 관리자 감시 기준과 개인 알림 수신 설정을 분리하세요. 감시 기준은
    # backend/app/settings/sql/monitoring_settings.sql의 필드와 단위를 맞추세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented(
        "감시 기준·개인 알림 설정 / get_monitoring_settings 구현 예정"
    )


def update_monitoring_settings(body: schemas.MonitoringSettingsRequest):
    # TODO: 관리자 감시 기준과 개인 알림 수신 설정을 분리하세요. 감시 기준은
    # backend/app/settings/sql/monitoring_settings.sql의 필드와 단위를 맞추세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented(
        "감시 기준·개인 알림 설정 / update_monitoring_settings 구현 예정"
    )


def update_notification_settings(body: schemas.NotificationSettingsRequest):
    # TODO: 관리자 감시 기준과 개인 알림 수신 설정을 분리하세요. 감시 기준은
    # backend/app/settings/sql/monitoring_settings.sql의 필드와 단위를 맞추세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented(
        "감시 기준·개인 알림 설정 / update_notification_settings 구현 예정"
    )
