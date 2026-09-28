"""
추가 지원요청: 현장 담당자의 요청을 등록하고 사건별 최신순으로 조회하세요. 작성자/소속은 인증 정보에서 결정합니다. 출동 완료·사건 종결 기능은 범위에
없습니다.
"""

from ..errors import FeatureNotImplemented
from . import schemas


def list_support_requests(incident_id: int):
    # TODO: 현장 담당자의 요청을 등록하고 사건별 최신순으로 조회하세요. 작성자/소속은 인증 정보에서 결정합니다. 출동 완료·사건 종결 기능은 범위에 없습니다.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("추가 지원요청 / list_support_requests 구현 예정")


def create_support_request(incident_id: int, body: schemas.SupportRequestCreate):
    # TODO: 현장 담당자의 요청을 등록하고 사건별 최신순으로 조회하세요. 작성자/소속은 인증 정보에서 결정합니다. 출동 완료·사건 종결 기능은 범위에 없습니다.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("추가 지원요청 / create_support_request 구현 예정")
