"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def list_agencies(connection, region_code: str | None = None):
    # TODO: 기관명·유형·지역·좌표 조회.
    raise FeatureNotImplemented("agencies.list_agencies DB 쿼리 구현 예정")


def list_recommendations(connection, incident_id: int):
    # TODO: incident_agency_recommendations와 agencies JOIN. 추천 순위 정렬.
    raise FeatureNotImplemented("agencies.list_recommendations DB 쿼리 구현 예정")


def save_delivery(connection, incident_id: int, selections: list[dict]):
    # TODO: 선택 기관별 전달 상태, 사용자별 notifications, 사건 SENT 상태를 한 트랜잭션으로 기록. 중복 전송 방지.
    raise FeatureNotImplemented("agencies.save_delivery DB 쿼리 구현 예정")
