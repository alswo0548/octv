"""기관 조회·추천·전달의 업무 처리 위치입니다. 미구현 함수의 예외는 그대로 유지합니다."""

from ..errors import FeatureNotImplemented
from ..db.session import get_connection
from . import repository, schemas


# DB 연결을 열고 Repository의 기관 목록을 반환합니다.
def list_agencies():
    with get_connection() as connection:
        return repository.list_agencies(connection)


def list_recommendations(incident_id: int):
    raise FeatureNotImplemented(
        "기관 조회·추천·선택 전달 / list_recommendations 구현 예정"
    )


def deliver(incident_id: int, body: schemas.DeliveryRequest):
    raise FeatureNotImplemented("기관 조회·추천·선택 전달 / deliver 구현 예정")
