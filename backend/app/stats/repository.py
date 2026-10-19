"""사건별 최신 평가 한 건을 붙여 집계합니다. UTC 구간 조회→KST 일·시간별 집계."""

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def aggregate_incidents(connection, filters: dict):
    # 확정 사건은 CONFIRMED/SENT/RESOLVED. 기관·경로 JOIN 없이 사건 중복을 방지합니다.
    conditions = ["i.detected_at >= %s", "i.detected_at < %s"]
    params = [filters["start_utc"], filters["end_utc"]]
    for key, column in (("region_code", "c.region_code"), ("cctv_id", "i.cctv_id")):
        if filters.get(key) is not None:
            conditions.append(f"{column} = %s")
            params.append(filters[key])
    if filters["confirmed_only"]:
        conditions.append("i.status IN ('CONFIRMED', 'SENT', 'RESOLVED')")
    query = """
        WITH filtered AS (
            SELECT i.id, i.hazard_type, i.status::text AS status, i.confidence,
                   i.detected_at + INTERVAL '9 hours' AS local_at,
                   COALESCE(a.risk_level, 'UNASSESSED') AS risk_level,
                   COALESCE(a.priority, 'UNASSESSED') AS priority
            FROM incidents i
            JOIN cctvs c ON c.id = i.cctv_id
            LEFT JOIN LATERAL (
                SELECT risk_level, priority FROM incident_assessments
                WHERE incident_id = i.id ORDER BY id DESC LIMIT 1
            ) a ON TRUE
            WHERE __WHERE__
        ), confidence AS (
            SELECT CASE WHEN confidence IS NULL OR confidence < 0 OR confidence > 1 THEN 'UNKNOWN'
                        WHEN confidence < 0.5 THEN '0-50'
                        WHEN confidence < 0.7 THEN '50-70'
                        WHEN confidence < 0.9 THEN '70-90'
                        WHEN confidence <= 1 THEN '90-100'
                        ELSE 'UNKNOWN' END AS label, COUNT(*) AS count
            FROM filtered GROUP BY 1
        )
        SELECT
            (SELECT COUNT(*) FROM filtered) AS total_incident_count,
            (SELECT COUNT(*) FROM filtered WHERE status IN ('CONFIRMED', 'SENT', 'RESOLVED')) AS confirmed_incident_count,
            (SELECT AVG(confidence) FROM filtered WHERE confidence BETWEEN 0 AND 1) AS average_confidence,
            COALESCE((SELECT json_object_agg(status, count) FROM (SELECT status, COUNT(*) AS count FROM filtered GROUP BY status) s), '{}'::json) AS by_status,
            COALESCE((SELECT json_object_agg(hazard_type, count) FROM (SELECT hazard_type, COUNT(*) AS count FROM filtered GROUP BY hazard_type) s), '{}'::json) AS by_hazard,
            COALESCE((SELECT json_object_agg(risk_level, count) FROM (SELECT risk_level, COUNT(*) AS count FROM filtered GROUP BY risk_level) s), '{}'::json) AS by_risk,
            COALESCE((SELECT json_object_agg(priority, count) FROM (SELECT priority, COUNT(*) AS count FROM filtered GROUP BY priority) s), '{}'::json) AS by_priority,
            COALESCE((SELECT json_object_agg(label, count) FROM confidence), '{}'::json) AS confidence_distribution,
            (SELECT json_agg(json_build_object('day', day::date, 'count', count) ORDER BY day)
             FROM (SELECT days.day, COUNT(f.id) AS count
                   FROM generate_series(%s::timestamp, %s::timestamp, INTERVAL '1 day') days(day)
                   LEFT JOIN filtered f ON f.local_at::date = days.day::date
                   GROUP BY days.day) daily) AS daily,
            (SELECT json_agg(json_build_object('hour', hour, 'count', count) ORDER BY hour)
             FROM (SELECT hours.hour, COUNT(f.id) AS count
                   FROM generate_series(0, 23) hours(hour)
                   LEFT JOIN filtered f ON EXTRACT(HOUR FROM f.local_at) = hours.hour
                   GROUP BY hours.hour) hourly) AS hourly
    """.replace("__WHERE__", " AND ".join(conditions))
    params.extend((filters["start"], filters["end"]))
    return connection.execute(query, tuple(params)).fetchone()
