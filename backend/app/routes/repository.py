"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def list_candidates(connection, incident_id: int, agency_id: int):
    # TODO: 기관 추천 → route_candidates JOIN. 사건과 기관이 일치하는 후보 3개/제외 사유 반환.
    raise FeatureNotImplemented("routes.list_candidates DB 쿼리 구현 예정")


def save_evaluation(connection, recommendation_id: int, evaluation: dict):
    # TODO: route_candidates에 후보별 점수·좌표·규칙 버전·생성시각·기관추천 ID를 저장.
    raise FeatureNotImplemented("routes.save_evaluation DB 쿼리 구현 예정")
