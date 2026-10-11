"""기관 관련 SQL의 실행 위치입니다. 미구현 함수의 예외는 그대로 유지합니다."""

from ..errors import FeatureNotImplemented


# 선택한 지역 조건을 적용하고 기관명·ID 순서로 조회합니다.
def list_agencies(connection, region_code: str | None = None):
    sql = "SELECT id, name, agency_type FROM agencies"
    params = []
    if region_code is not None:
        sql += " WHERE region_code = %s"
        params.append(region_code)
    return connection.execute(sql + " ORDER BY name, id", params).fetchall()


def list_recommendations(connection, incident_id: int):
    raise FeatureNotImplemented("agencies.list_recommendations DB 쿼리 구현 예정")


def save_delivery(connection, incident_id: int, selections: list[dict]):
    raise FeatureNotImplemented("agencies.save_delivery DB 쿼리 구현 예정")
