"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def list_for_user(connection, user_id: int):
    # TODO: notifications에서 본인 user_id만 조회. incidents_id 이름 유지, 최신순 정렬.
    raise FeatureNotImplemented("notifications.list_for_user DB 쿼리 구현 예정")


def mark_read(connection, notification_id: int, user_id: int):
    # TODO: 본인 알림인지 WHERE 조건으로 확인한 뒤 read_at 갱신.
    raise FeatureNotImplemented("notifications.mark_read DB 쿼리 구현 예정")
