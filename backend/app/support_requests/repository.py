"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def list_for_incident(connection, incident_id: int):
    # TODO: incident_support_requests 조회. created_at DESC, id DESC로 최신 요청 우선.
    raise FeatureNotImplemented("support_requests.list_for_incident DB 쿼리 구현 예정")


def insert_request(
    connection, incident_id: int, responder_id: int, agency_id: int, data: dict
):
    # TODO: 인증 정보의 사용자/소속으로 요청 등록. 클라이언트가 작성자를 임의 지정하지 못하게 처리.
    raise FeatureNotImplemented("support_requests.insert_request DB 쿼리 구현 예정")
