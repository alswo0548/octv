"""
기관별 후보 경로: 사건·기관별 A/B/C 후보 3개와 평가 근거를 조회하세요. 제외 경로도 반환하되 네비게이션 사용 가능 여부를 분리하세요. 실제 경로 계산은
AI/외부 연동에서 처리합니다.
"""

from ..errors import FeatureNotImplemented
from . import schemas


def list_candidates(incident_id: int, agency_id: int):
    # TODO: 사건·기관별 A/B/C 후보 3개와 평가 근거를 조회하세요. 제외 경로도 반환하되 네비게이션 사용 가능 여부를 분리하세요. 실제 경로
    # 계산은 AI/외부 연동에서 처리합니다.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("기관별 후보 경로 / list_candidates 구현 예정")
