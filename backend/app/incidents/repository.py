"""사건 저장·중복 갱신과 목록·상세 조회 SQL을 실행합니다.
Service에서 받은 연결을 사용하며, 트랜잭션은 Service의 get_connection 블록이 관리합니다."""

from uuid import uuid4

from psycopg.types.json import Jsonb


# 오탐 처리 직후 같은 장면이 계속 탐지될 때
# 새 Incident가 즉시 다시 생기는 것을 막기 위한 재활성화 간격입니다.
#
# FALSE_POSITIVE 상태의 같은 dedup_key가 계속 탐지되면
# last_detected_at만 갱신하면서 억제 상태를 유지합니다.
#
# 탐지가 이 시간보다 오래 끊긴 뒤 다시 발생하면
# 새로운 Incident 생성이 허용됩니다.
FALSE_POSITIVE_REARM_SECONDS = 60


def suppress_recent_false_positive(
    connection,
    candidate: dict,
):
    """최근 오탐과 동일한 탐지라면 새 사건 생성을 억제합니다."""

    return connection.execute(
        """
        UPDATE incidents
        SET last_detected_at = GREATEST(
            last_detected_at,
            %s
        )
        WHERE id = (
            SELECT id
            FROM incidents
            WHERE cctv_id = %s
              AND hazard_type = %s
              AND dedup_key = %s
              AND status = 'FALSE_POSITIVE'
              AND last_detected_at >= (
                  %s
                  - (%s * INTERVAL '1 second')
              )
            ORDER BY
                last_detected_at DESC,
                id DESC
            LIMIT 1
        )
        RETURNING *
        """,
        (
            candidate["detected_at"],
            candidate["cctv_id"],
            candidate["hazard_type"],
            candidate["dedup_key"],
            candidate["detected_at"],
            FALSE_POSITIVE_REARM_SECONDS,
        ),
    ).fetchone()


# 새 사건을 저장하거나, 같은 진행 사건의 최근 탐지 시각만 갱신합니다.
def save_detection(
    connection,
    candidate: dict,
):
    # --------------------------------------------------------
    # 오탐 처리된 동일 장면 재생성 방지
    # --------------------------------------------------------
    suppressed = suppress_recent_false_positive(
        connection,
        candidate,
    )

    if suppressed is not None:
        return suppressed

    representative_image = candidate.get(
        "representative_image"
    )

    params = {
        **candidate,
        "incident_no": (
            "OCTV-" + uuid4().hex
        ),
        "bbox": Jsonb(
            candidate["detection_bbox_json"]
        ),
        "representative_image":
            representative_image,
        "representative_image_updated_at": (
            candidate["detected_at"]
            if representative_image is not None
            else None
        ),
    }

    return connection.execute(
        """
        INSERT INTO incidents (
            incident_no,
            cctv_id,
            hazard_type,
            confidence,
            model_version,
            representative_image,
            representative_image_updated_at,
            detection_bbox_json,
            dedup_key,
            detected_at,
            last_detected_at
        )
        VALUES (
            %(incident_no)s,
            %(cctv_id)s,
            %(hazard_type)s,
            %(confidence)s,
            %(model_version)s,
            %(representative_image)s,
            %(representative_image_updated_at)s,
            %(bbox)s,
            %(dedup_key)s,
            %(detected_at)s,
            %(detected_at)s
        )
        ON CONFLICT (
            cctv_id,
            hazard_type,
            dedup_key
        )
            WHERE status IN (
                'DETECTED',
                'CONFIRMED',
                'SENT'
            )
        DO UPDATE SET
            last_detected_at = GREATEST(
                incidents.last_detected_at,
                EXCLUDED.last_detected_at
            ),
            representative_image = CASE
                WHEN
                    EXCLUDED.representative_image
                    IS NOT NULL
                    AND (
                        incidents.representative_image_updated_at
                        IS NULL
                        OR
                        EXCLUDED.representative_image_updated_at
                        >=
                        incidents.representative_image_updated_at
                    )
                THEN
                    EXCLUDED.representative_image
                ELSE
                    incidents.representative_image
            END,
            representative_image_updated_at = CASE
                WHEN
                    EXCLUDED.representative_image
                    IS NOT NULL
                    AND (
                        incidents.representative_image_updated_at
                        IS NULL
                        OR
                        EXCLUDED.representative_image_updated_at
                        >=
                        incidents.representative_image_updated_at
                    )
                THEN
                    EXCLUDED.representative_image_updated_at
                ELSE
                    incidents.representative_image_updated_at
            END
        RETURNING *
        """,
        params,
    ).fetchone()


# 각 사건에 최신 평가 1건을 붙이며,
# 평가가 없어도 사건은 조회합니다.
#
# LEFT JOIN LATERAL을 사용하여
# incident_assessments가 여러 건이어도
# 가장 최근 평가 하나만 붙입니다.
READ_SQL = """
SELECT
    i.id,
    i.incident_no,
    i.cctv_id,
    i.hazard_type,
    i.confidence,
    i.model_version,
    i.detection_bbox_json,
    i.dedup_key,
    i.status,
    i.detected_at,
    i.last_detected_at,
    i.representative_image_updated_at,
    c.name AS cctv_name,
    c.latitude,
    c.longitude,
    c.region_code,
    c.provider,
    c.address,
    a.risk_score,
    a.risk_level,
    a.priority_score,
    a.priority,
    a.risk_breakdown_json,
    a.priority_breakdown_json,
    a.rule_version
FROM incidents i
JOIN cctvs c
    ON c.id = i.cctv_id
LEFT JOIN LATERAL (
    SELECT *
    FROM incident_assessments a
    WHERE a.incident_id = i.id
    ORDER BY a.id DESC
    LIMIT 1
) a ON TRUE
"""


# 사용자가 사건 목록에서 검색하거나
# 필터를 선택했을 때 사용합니다.
def incident_where(
    filters: dict,
):
    clauses = [
        "TRUE"
    ]
    params = []

    # --------------------------------------------------------
    # 기본 목록에서는 오탐 제외
    #
    # 단 status=FALSE_POSITIVE를 명시적으로 요청하면
    # 오탐 이력 조회가 가능합니다.
    # --------------------------------------------------------
    if filters.get("status") is None:
        clauses.append(
            "i.status <> 'FALSE_POSITIVE'"
        )
    else:
        clauses.append(
            "i.status = %s"
        )
        params.append(
            filters["status"]
        )

    for key, column in (
        (
            "hazard_type",
            "i.hazard_type",
        ),
        (
            "priority",
            "a.priority",
        ),
        (
            "region_code",
            "c.region_code",
        ),
        (
            "cctv_id",
            "i.cctv_id",
        ),
    ):
        if filters.get(key) is not None:
            clauses.append(
                column + " = %s"
            )
            params.append(
                filters[key]
            )

    if filters.get(
        "confirmed_only"
    ):
        clauses.append(
            """
            i.status IN (
                'CONFIRMED',
                'SENT',
                'RESOLVED'
            )
            """
        )

    if filters.get(
        "active_only"
    ):
        clauses.append(
            """
            i.status IN (
                'DETECTED',
                'CONFIRMED',
                'SENT'
            )
            """
        )

    # 기간은 시작 시각 포함,
    # 종료 시각은 제외합니다.
    for key, operator in (
        (
            "start",
            ">=",
        ),
        (
            "end",
            "<",
        ),
    ):
        if filters.get(key) is not None:
            clauses.append(
                "i.detected_at "
                + operator
                + " %s"
            )
            params.append(
                filters[key]
            )

    if filters.get("q"):
        clauses.append(
            """
            (
                i.incident_no ILIKE %s
                OR
                c.name ILIKE %s
            )
            """
        )

        params.extend(
            [
                "%"
                + filters["q"]
                + "%",
                "%"
                + filters["q"]
                + "%",
            ]
        )

    return (
        " AND ".join(
            clauses
        ),
        params,
    )


# 인증 사용자 기관의 전달 관계로
# 조회 범위를 제한합니다.
def agency_filter(
    filters: dict,
):
    if "agency_id" not in filters:
        return (
            "TRUE",
            [],
        )

    # 기관 미지정 사용자가
    # 전체 사건을 보지 못하게 합니다.
    if filters["agency_id"] is None:
        return (
            "FALSE",
            [],
        )

    status_clause = (
        """
        ar.recommendation_status
        IN ('DELIVERED', 'COMPLETED')
        """
    )

    if filters.get(
        "agency_active_only"
    ):
        status_clause = (
            """
            ar.recommendation_status
            = 'DELIVERED'
            """
        )

    clause = (
        """
        EXISTS (
            SELECT 1
            FROM incident_agency_recommendations ar
            WHERE ar.incident_id = i.id
              AND ar.agency_id = %s
              AND
        """
        + status_clause
        + """
        )
        """
    )

    return (
        clause,
        [
            filters["agency_id"]
        ],
    )


# OCTV 상황실 WEB 사건 목록
def list_incidents(
    connection,
    filters: dict,
    page: int,
    page_size: int,
):
    where, params = (
        incident_where(
            filters
        )
    )

    scoped_where, scoped_params = (
        agency_filter(
            filters
        )
    )

    where = (
        "("
        + where
        + ") AND ("
        + scoped_where
        + ")"
    )

    params += scoped_params

    base = (
        READ_SQL
        + " WHERE "
        + where
    )

    total = connection.execute(
        """
        SELECT count(*) AS n
        FROM (
        """
        + base
        + """
        ) q
        """,
        params,
    ).fetchone()["n"]

    # --------------------------------------------------------
    # 관제 목록 정렬
    #
    # 1. 아직 확인하지 않은 DETECTED 사건 우선
    # 2. DETECTED 내부에서는 최신 사건 우선
    # 3. 그 외는 우선순위 점수 높은 순
    # 4. 같은 우선순위에서는 최신 사건 우선
    # --------------------------------------------------------
    items = connection.execute(
        base
        + """
        ORDER BY
            CASE
                WHEN i.status = 'DETECTED'
                THEN 0
                ELSE 1
            END,
            CASE
                WHEN i.status = 'DETECTED'
                THEN i.detected_at
                ELSE NULL
            END DESC NULLS LAST,
            a.priority_score DESC NULLS LAST,
            i.detected_at DESC,
            i.id DESC
        LIMIT %s
        OFFSET %s
        """,
        [
            *params,
            page_size,
            (
                page - 1
            )
            * page_size,
        ],
    ).fetchall()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# 기관 사용자 상세 접근 권한 확인
def find_agency_access(
    connection,
    incident_id: int,
    agency_id: int,
):
    return connection.execute(
        """
        SELECT id
        FROM incident_agency_recommendations
        WHERE incident_id = %s
          AND agency_id = %s
          AND recommendation_status
              IN ('DELIVERED', 'COMPLETED')
        """,
        (
            incident_id,
            agency_id,
        ),
    ).fetchone()


# 사건 현재 상태만 조회
def find_status(
    connection,
    incident_id: int,
):
    return connection.execute(
        """
        SELECT
            id,
            status
        FROM incidents
        WHERE id = %s
        """,
        (
            incident_id,
        ),
    ).fetchone()


# 허용된 상태에서만 상태 전이
def update_status(
    connection,
    incident_id: int,
    target_status: str,
    allowed_from: tuple[str, ...],
):
    if not allowed_from:
        raise ValueError(
            "allowed_from은 비어 있을 수 없습니다."
        )

    placeholders = ", ".join(
        [
            "%s::incident_status_enum"
            for _ in allowed_from
        ]
    )

    query = f"""
        UPDATE incidents
        SET status = %s::incident_status_enum
        WHERE id = %s
          AND status IN ({placeholders})
        RETURNING
            id,
            status
    """

    return connection.execute(
        query,
        (
            target_status,
            incident_id,
            *allowed_from,
        ),
    ).fetchone()


def find_detail(
    connection,
    incident_id: int,
):
    return connection.execute(
        READ_SQL
        + " WHERE i.id = %s",
        (
            incident_id,
        ),
    ).fetchone()


def find_representative_image(
    connection,
    incident_id: int,
):
    return connection.execute(
        """
        SELECT
            representative_image,
            representative_image_updated_at
        FROM incidents
        WHERE id = %s
        """,
        (
            incident_id,
        ),
    ).fetchone()