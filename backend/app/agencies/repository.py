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


# 04번 06 코드 · 사건별 후보 기관 저장 (기존 UNIQUE 재사용)
from psycopg.types.json import Jsonb


def save_recommendation(connection, incident_id, recommendation):
    p = {
        **recommendation,
        'incident_id': incident_id,
        'breakdown': Jsonb(recommendation['score_breakdown_json']),
    }
    return connection.execute(
        """
        INSERT INTO incident_agency_recommendations (
            incident_id, agency_id, recommendation_rank,
            recommendation_score, score_breakdown_json, rule_version
        )
        VALUES (
            %(incident_id)s, %(agency_id)s, %(recommendation_rank)s,
            %(recommendation_score)s, %(breakdown)s, %(rule_version)s
        )
        ON CONFLICT (incident_id, agency_id)
        DO UPDATE SET
            recommendation_rank = EXCLUDED.recommendation_rank,
            recommendation_score = EXCLUDED.recommendation_score,
            score_breakdown_json = EXCLUDED.score_breakdown_json,
            rule_version = EXCLUDED.rule_version
        RETURNING *
        """,
        p,
    ).fetchone()


def list_analysis_agencies(connection):
    return connection.execute('SELECT * FROM agencies ORDER BY id').fetchall()
