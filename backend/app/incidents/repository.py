"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def list_incidents(connection, filters: dict, page: int, page_size: int):
    # TODO: incidents와 incident_assessments JOIN. WHERE 조건·전체 건수·안정적인 정렬·LIMIT/OFFSET.
    raise FeatureNotImplemented("incidents.list_incidents DB 쿼리 구현 예정")


def find_detail(connection, incident_id: int):
    # TODO: 사건·CCTV·외부 상황·평가·최신 지원요청을 조회. 없는 ID 처리.
    raise FeatureNotImplemented("incidents.find_detail DB 쿼리 구현 예정")


def save_detection(connection, candidate: dict):
    # TODO: 중복 사건은 last_detected_at 갱신, 신규는 등록. dedup_key 동시성 정책 먼저 합의.
    raise FeatureNotImplemented("incidents.save_detection DB 쿼리 구현 예정")
