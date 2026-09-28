"""
사건 전달 알림: 로그인 사용자에게 전달된 사건 알림만 조회하고 읽음 시각을 기록하세요. 알림 종류를 임의 확대하지 마세요. 실제 푸시 전송은 연동 구현 후
연결하세요.
"""

from ..errors import FeatureNotImplemented
from . import schemas


def list_notifications():
    # TODO: 로그인 사용자에게 전달된 사건 알림만 조회하고 읽음 시각을 기록하세요. 알림 종류를 임의 확대하지 마세요. 실제 푸시 전송은 연동 구현 후
    # 연결하세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("사건 전달 알림 / list_notifications 구현 예정")


def mark_read(notification_id: int):
    # TODO: 로그인 사용자에게 전달된 사건 알림만 조회하고 읽음 시각을 기록하세요. 알림 종류를 임의 확대하지 마세요. 실제 푸시 전송은 연동 구현 후
    # 연결하세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("사건 전달 알림 / mark_read 구현 예정")
