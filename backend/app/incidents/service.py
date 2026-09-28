"""사건 조회·상세: 상태·유형·우선순위·기간·검색과 서버 페이지네이션을 구현하세요. AI 사건 등록은 내부 호출로 분리하고 중복 판별 기준을 합의하세요."""

from ..errors import FeatureNotImplemented
from . import schemas


def list_incidents(page: int = 1, page_size: int = 5):
    # TODO: 상태·유형·우선순위·기간·검색과 서버 페이지네이션을 구현하세요. AI 사건 등록은 내부 호출로 분리하고 중복 판별 기준을 합의하세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("사건 조회·상세 / list_incidents 구현 예정")


def get_incident(incident_id: int):
    # TODO: 상태·유형·우선순위·기간·검색과 서버 페이지네이션을 구현하세요. AI 사건 등록은 내부 호출로 분리하고 중복 판별 기준을 합의하세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("사건 조회·상세 / get_incident 구현 예정")
