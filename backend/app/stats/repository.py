"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def aggregate_incidents(connection, filters: dict):
    # TODO: 확정 사건 기준으로 유형/일자 집계. SENT를 포함할지 등 화면 기준을 합의하고 JOIN 중복 집계를 방지.
    raise FeatureNotImplemented("stats.aggregate_incidents DB 쿼리 구현 예정")
