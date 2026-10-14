"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


# 04번 07 코드 · 기존 경로 테이블 저장과 조회
from psycopg.types.json import Jsonb


def list_candidates(connection, incident_id: int, agency_id: int):
    return connection.execute(
        """
        SELECT r.* FROM route_candidates r
        JOIN incident_agency_recommendations ar
            ON ar.id = r.agency_recommendation_id
        WHERE ar.incident_id = %s AND ar.agency_id = %s
        ORDER BY
            (r.disqualify_reason IS NOT NULL),
            CASE r.score_breakdown_json ->> 'verification_status'
                WHEN 'VERIFIED' THEN 0
                WHEN 'NEEDS_REVIEW' THEN 1
                ELSE 2
            END,
            r.total_score DESC NULLS LAST,
            r.id
        """,
        (incident_id, agency_id),
    ).fetchall()


def save_evaluation(connection, recommendation_id: int, evaluation: dict):
    p = {
        **evaluation,
        'recommendation_id': recommendation_id,
        'path': Jsonb(evaluation['route_path_json']),
        'breakdown': Jsonb(evaluation['score_breakdown_json']),
    }
    return connection.execute(
        """
        INSERT INTO route_candidates (
            route_name, distance_m, duration_sec, total_score,
            score_breakdown_json, disqualify_reason, route_path_json,
            rule_version, agency_recommendation_id
        )
        VALUES (
            %(route_name)s, %(distance_m)s, %(duration_sec)s, %(total_score)s,
            %(breakdown)s, %(disqualify_reason)s, %(path)s,
            %(rule_version)s, %(recommendation_id)s
        )
        RETURNING *
        """,
        p,
    ).fetchone()
