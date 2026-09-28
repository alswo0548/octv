"""
기관 조회·추천·선택 전달: 조회 기관과 전달 대상 기관을 분리하세요. 선택 기관에 사건·경로 정보를 전달하고 알림과 처리 상태를 한 트랜잭션으로 기록하세요.
출동 지령·인원 배정은 하지 않습니다.
"""

from ..errors import FeatureNotImplemented
from . import schemas


def list_agencies():
    # TODO: 조회 기관과 전달 대상 기관을 분리하세요. 선택 기관에 사건·경로 정보를 전달하고 알림과 처리 상태를 한 트랜잭션으로 기록하세요. 출동
    # 지령·인원 배정은 하지 않습니다.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("기관 조회·추천·선택 전달 / list_agencies 구현 예정")


def list_recommendations(incident_id: int):
    # TODO: 조회 기관과 전달 대상 기관을 분리하세요. 선택 기관에 사건·경로 정보를 전달하고 알림과 처리 상태를 한 트랜잭션으로 기록하세요. 출동
    # 지령·인원 배정은 하지 않습니다.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented(
        "기관 조회·추천·선택 전달 / list_recommendations 구현 예정"
    )


def deliver(incident_id: int, body: schemas.DeliveryRequest):
    # TODO: 조회 기관과 전달 대상 기관을 분리하세요. 선택 기관에 사건·경로 정보를 전달하고 알림과 처리 상태를 한 트랜잭션으로 기록하세요. 출동
    # 지령·인원 배정은 하지 않습니다.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("기관 조회·추천·선택 전달 / deliver 구현 예정")
