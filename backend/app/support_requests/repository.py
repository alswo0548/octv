
"""
추가 지원요청 정보를 PostgreSQL에서 조회·저장하는 Repository.

주요 기능
1. find_access_scope(): 사건 존재 여부와 기관 전달 상태 조회
2. list_for_incident(): 사건별 추가 지원요청을 최신순으로 조회
3. insert_request(): 전달된 사건에 추가 지원요청 저장
4. users·agencies 테이블에서 작성자와 기관 이름 조회

전체 흐름
Service → Repository → PostgreSQL → Service

주의사항
- 기존 incident_support_requests 테이블과 support_type_enum 재사용
- 관리자 조회는 사건의 전체 요청, 기관 사용자는 자기 기관 요청만 조회
- INSERT 시 사건 SENT·기관 DELIVERED·사용자 활성 상태 재확인
- 작성자·기관 ID는 인증된 사용자 정보로 전달받음
- SQL 입력값은 파라미터 바인딩 사용
- DB 연결과 COMMIT·ROLLBACK은 Service에서 관리
- 기존 DB 구조와 기관·사건 상태를 변경하지 않음
"""


# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def find_access_scope(connection, incident_id: int, agency_id: int | None):
    """사건 존재와 인증 기관의 전달/완료 상태를 한 번에 확인합니다."""
    return connection.execute(
        """
        SELECT i.id, i.status AS incident_status,
               ar.recommendation_status
        FROM incidents i
        LEFT JOIN incident_agency_recommendations ar
          ON ar.incident_id = i.id AND ar.agency_id = %s
        WHERE i.id = %s
        """,
        (agency_id, incident_id),
    ).fetchone()


def list_for_incident(connection, incident_id: int, agency_id: int | None = None):
    where_agency = "" if agency_id is None else " AND sr.agency_id = %s"
    params = (incident_id,) if agency_id is None else (incident_id, agency_id)
    return connection.execute(
        """
        SELECT sr.id, sr.incident_id, sr.responder_id, sr.agency_id,
               sr.support_type, sr.request_content, sr.created_at,
               u.name AS responder_name, a.name AS agency_name
        FROM incident_support_requests sr
        JOIN users u ON u.id = sr.responder_id
        JOIN agencies a ON a.id = sr.agency_id
        WHERE sr.incident_id = %s
        """
        + where_agency
        + " ORDER BY sr.created_at DESC, sr.id DESC",
        params,
    ).fetchall()


def insert_request(
    connection, incident_id: int, responder_id: int, agency_id: int, data: dict
):
    result = connection.execute(
        """
        INSERT INTO incident_support_requests (
            incident_id, responder_id, agency_id, support_type,
            request_content, created_at
        )
        SELECT i.id, u.id, ar.agency_id,
               %s::support_type_enum, %s, (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
        FROM incidents i
        JOIN incident_agency_recommendations ar ON ar.incident_id = i.id
        JOIN users u ON u.id = %s AND u.agency_id = ar.agency_id
        WHERE i.id = %s
          AND i.status = 'SENT'
          AND ar.agency_id = %s
          AND ar.recommendation_status = 'DELIVERED'
          AND u.is_active = TRUE
          AND u.role IN ('AGENCY_STAFF', 'RESPONDER')
        RETURNING id, incident_id, responder_id, agency_id,
                  support_type, request_content, created_at
        """,
        (
            data["support_type"], data["request_content"],
            responder_id, incident_id, agency_id,
        ),
    ).fetchone()
    if result is None:
        return None
    # 응답에 사용하는 이름은 토큰 또는 클라이언트가 아닌 DB의 현재 이름을 조회합니다.
    names = connection.execute(
        """
        SELECT u.name AS responder_name, a.name AS agency_name
        FROM users u JOIN agencies a ON a.id = u.agency_id
        WHERE u.id = %s AND a.id = %s
        """,
        (responder_id, agency_id),
    ).fetchone()
    return {**result, **(names or {})}
