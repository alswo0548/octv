"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def list_cctvs(connection, region_code: str | None = None):
    # TODO: cctvs와 region 조회. 감시 상태와 연결 상태를 각각 반환.
    raise FeatureNotImplemented("cctvs.list_cctvs DB 쿼리 구현 예정")


def update_monitoring(connection, cctv_id: int, enabled: bool, mode: str | None):
    # TODO: 특보/권한을 서비스에서 확인한 후 기본 감시 대상 여부와 현재 모드의 의미를 구분해 저장. 동시 변경 충돌 고려.
    raise FeatureNotImplemented("cctvs.update_monitoring DB 쿼리 구현 예정")
