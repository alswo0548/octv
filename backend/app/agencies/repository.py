"""
기관 조회·LangGraph 추천 저장 및 선택 기관 전달과 DB 알림을 처리합니다.

주요 기능
- 회원가입용 기관 목록 조회
- 사건별 추천 기관과 경로 후보 조회
- 역할에 따른 추천 기관 조회 범위 제한
- 추천 기관·경로 소속 검사
- 선택 기관 전달
- DB 알림 생성
"""

from typing import Any

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .schemas import DeliverySelection


# ------------------------------------------------------------
# 회원가입용 기관 목록
# ------------------------------------------------------------

def list_agencies(
    connection,
    region_code: str | None = None,
):
    sql = """
        SELECT
            id,
            name,
            agency_type
        FROM agencies
    """

    params = []

    if region_code is not None:
        sql += """
            WHERE region_code = %s
        """
        params.append(
            region_code
        )

    sql += """
        ORDER BY name, id
    """

    return connection.execute(
        sql,
        params,
    ).fetchall()


# ------------------------------------------------------------
# 사건별 추천 기관 / 경로 후보 조회
# ------------------------------------------------------------

def list_recommendations(
    connection,
    incident_id: int,
    *,
    agency_id: int | None = None,
):
    """
    저장된 추천 기관과 경로 후보를 조회한다.

    agency_id=None:
        CONTROL_ADMIN용.
        해당 사건의 모든 추천 기관과 경로를 반환한다.

    agency_id가 있는 경우:
        AGENCY_STAFF / RESPONDER용.
        자신의 기관에 DELIVERED 또는 COMPLETED된
        추천과 경로만 반환한다.

        자신의 기관에 전달되지 않은 사건은
        존재 여부를 노출하지 않도록 404 처리한다.
    """

    incident = connection.execute(
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

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="사건이 없습니다.",
        )

    # --------------------------------------------------------
    # 관제 관리자
    # --------------------------------------------------------

    if agency_id is None:
        recommendations = (
            connection.execute(
                """
                SELECT
                    ar.id AS agency_recommendation_id,
                    ar.agency_id,
                    a.name AS agency_name,
                    a.agency_type,
                    ar.recommendation_rank,
                    ar.recommendation_score,
                    ar.recommendation_status,
                    ar.score_breakdown_json,
                    ar.rule_version

                FROM incident_agency_recommendations AS ar

                JOIN agencies AS a
                  ON a.id = ar.agency_id

                WHERE ar.incident_id = %s

                ORDER BY
                    ar.recommendation_rank,
                    ar.agency_id
                """,
                (
                    incident_id,
                ),
            )
            .fetchall()
        )

        routes = (
            connection.execute(
                """
                SELECT
                    r.id,
                    r.agency_recommendation_id,
                    r.route_name,
                    r.distance_m,
                    r.duration_sec,
                    r.total_score,
                    r.score_breakdown_json,
                    r.disqualify_reason,
                    r.route_path_json,
                    r.rule_version

                FROM route_candidates AS r

                JOIN incident_agency_recommendations AS ar
                  ON ar.id = r.agency_recommendation_id

                WHERE ar.incident_id = %s

                ORDER BY
                    r.agency_recommendation_id,
                    (
                        r.disqualify_reason
                        IS NOT NULL
                    ),
                    CASE
                        r.score_breakdown_json
                        ->> 'verification_status'

                        WHEN 'VERIFIED'
                            THEN 0

                        WHEN 'NEEDS_REVIEW'
                            THEN 1

                        ELSE 2
                    END,
                    r.total_score DESC NULLS LAST,
                    r.id
                """,
                (
                    incident_id,
                ),
            )
            .fetchall()
        )

    # --------------------------------------------------------
    # 기관 담당자 / 현장 담당자
    # --------------------------------------------------------

    else:
        recommendations = (
            connection.execute(
                """
                SELECT
                    ar.id AS agency_recommendation_id,
                    ar.agency_id,
                    a.name AS agency_name,
                    a.agency_type,
                    ar.recommendation_rank,
                    ar.recommendation_score,
                    ar.recommendation_status,
                    ar.score_breakdown_json,
                    ar.rule_version

                FROM incident_agency_recommendations AS ar

                JOIN agencies AS a
                  ON a.id = ar.agency_id

                WHERE ar.incident_id = %s
                  AND ar.agency_id = %s
                  AND ar.recommendation_status
                      IN (
                          'DELIVERED',
                          'COMPLETED'
                      )

                ORDER BY
                    ar.recommendation_rank,
                    ar.agency_id
                """,
                (
                    incident_id,
                    agency_id,
                ),
            )
            .fetchall()
        )

        if not recommendations:
            raise HTTPException(
                status_code=404,
                detail=(
                    "사건이 없거나 "
                    "소속 기관에 전달되지 않았습니다."
                ),
            )

        routes = (
            connection.execute(
                """
                SELECT
                    r.id,
                    r.agency_recommendation_id,
                    r.route_name,
                    r.distance_m,
                    r.duration_sec,
                    r.total_score,
                    r.score_breakdown_json,
                    r.disqualify_reason,
                    r.route_path_json,
                    r.rule_version

                FROM route_candidates AS r

                JOIN incident_agency_recommendations AS ar
                  ON ar.id = r.agency_recommendation_id

                WHERE ar.incident_id = %s
                  AND ar.agency_id = %s
                  AND ar.recommendation_status
                      IN (
                          'DELIVERED',
                          'COMPLETED'
                      )

                ORDER BY
                    r.agency_recommendation_id,
                    (
                        r.disqualify_reason
                        IS NOT NULL
                    ),
                    CASE
                        r.score_breakdown_json
                        ->> 'verification_status'

                        WHEN 'VERIFIED'
                            THEN 0

                        WHEN 'NEEDS_REVIEW'
                            THEN 1

                        ELSE 2
                    END,
                    r.total_score DESC NULLS LAST,
                    r.id
                """,
                (
                    incident_id,
                    agency_id,
                ),
            )
            .fetchall()
        )

    # --------------------------------------------------------
    # 경로를 추천 기관별로 묶기
    # --------------------------------------------------------

    routes_by_recommendation: dict[
        int,
        list[dict],
    ] = {}

    for route in routes:
        routes_by_recommendation.setdefault(
            route[
                "agency_recommendation_id"
            ],
            [],
        ).append(
            route
        )

    return {
        "incident_id":
            incident_id,

        "incident_status":
            incident[
                "status"
            ],

        "items": [
            {
                **row,

                "routes":
                    routes_by_recommendation.get(
                        row[
                            "agency_recommendation_id"
                        ],
                        [],
                    ),
            }

            for row in recommendations
        ],
    }


# ------------------------------------------------------------
# 기관 전달
# ------------------------------------------------------------

def save_delivery(
    connection: Any,
    incident_id: int,
    selections: list[
        DeliverySelection
    ],
) -> tuple[
    dict,
    list[int],
]:
    """
    하나의 DB 트랜잭션에서
    선택한 기관들을 검증하고 전달한다.
    """

    connection.execute(
        "SET LOCAL TIME ZONE 'UTC'"
    )

    incident = (
        _lock_deliverable_incident(
            connection,
            incident_id,
        )
    )

    validated: list[
        dict
    ] = []

    # 교착 가능성을 줄이기 위해
    # 기관 ID 순서대로 잠금한다.
    for selection in sorted(
        selections,
        key=lambda item: item.agency_id,
    ):
        recommendation = (
            _lock_recommendation(
                connection,
                incident_id,
                selection.agency_id,
            )
        )

        _validate_optional_route(
            connection,
            recommendation[
                "id"
            ],
            selection.route_candidate_id,
        )

        if (
            recommendation[
                "recommendation_status"
            ]
            not in (
                "RECOMMENDED",
                "DELIVERED",
                "COMPLETED",
            )
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "처리할 수 없는 "
                    "기관 전달 상태입니다."
                ),
            )

        validated.append(
            recommendation
        )

    items: list[
        dict
    ] = []

    notification_ids: list[
        int
    ] = []

    for recommendation in validated:
        previous_status = (
            recommendation[
                "recommendation_status"
            ]
        )

        newly_delivered = (
            previous_status
            == "RECOMMENDED"
        )

        new_notifications: list[
            dict
        ] = []

        if newly_delivered:
            connection.execute(
                """
                UPDATE
                    incident_agency_recommendations

                SET
                    recommendation_status
                        = 'DELIVERED'

                WHERE id = %s
                  AND recommendation_status
                      = 'RECOMMENDED'
                """,
                (
                    recommendation[
                        "id"
                    ],
                ),
            )

            new_notifications = (
                _create_delivery_notifications(
                    connection,
                    incident_id,
                    recommendation,
                )
            )

            notification_ids.extend(
                row["id"]
                for row
                in new_notifications
            )

        items.append(
            {
                "agency_id":
                    recommendation[
                        "agency_id"
                    ],

                "agency_recommendation_id":
                    recommendation[
                        "id"
                    ],

                "status": (
                    "DELIVERED"
                    if newly_delivered
                    else previous_status
                ),

                "newly_delivered":
                    newly_delivered,

                "created_notification_count":
                    len(
                        new_notifications
                    ),
            }
        )

    incident_status = (
        incident[
            "status"
        ]
    )

    if (
        incident_status
        == "CONFIRMED"
        and any(
            item["status"]
            == "DELIVERED"
            for item
            in items
        )
    ):
        connection.execute(
            """
            UPDATE incidents
            SET status = 'SENT'
            WHERE id = %s
              AND status = 'CONFIRMED'
            """,
            (
                incident_id,
            ),
        )

        incident_status = (
            "SENT"
        )

    # 잠금 순서와 관계없이
    # 사용자 선택 순서대로 응답
    items_by_agency = {
        item["agency_id"]:
            item

        for item
        in items
    }

    result = {
        "incident_id":
            incident_id,

        "incident_status":
            incident_status,

        "items": [
            items_by_agency[
                selection.agency_id
            ]

            for selection
            in selections
        ],

        "created_notification_count":
            len(
                notification_ids
            ),

        "push_status":
            "NOT_QUEUED",
    }

    return (
        result,
        notification_ids,
    )


# ------------------------------------------------------------
# 현장 대응 완료
# ------------------------------------------------------------

def complete_delivery(
    connection: Any,
    incident_id: int,
    agency_id: int,
) -> dict:
    """
    현장대응자의 소속 기관에 전달된 사건을
    DELIVERED → COMPLETED 상태로 변경한다.

    같은 사건에 대한 기관 전달/완료 작업의
    잠금 순서를 맞추기 위해 Incident를 먼저 잠근다.
    """

    # --------------------------------------------------------
    # 1. Incident 잠금
    # --------------------------------------------------------

    incident = (
        connection.execute(
            """
            SELECT
                id,
                status
            FROM incidents
            WHERE id = %s
            FOR UPDATE
            """,
            (
                incident_id,
            ),
        )
        .fetchone()
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="사건이 없습니다.",
        )

    if incident["status"] not in (
        "SENT",
        "RESOLVED",
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "기관에 전달된 사건만 "
                "대응 완료 처리할 수 있습니다."
            ),
        )

    # --------------------------------------------------------
    # 2. 로그인 사용자의 기관 전달 건 잠금
    # --------------------------------------------------------

    recommendation = (
        connection.execute(
            """
            SELECT
                id,
                agency_id,
                recommendation_status
            FROM incident_agency_recommendations
            WHERE incident_id = %s
              AND agency_id = %s
            FOR UPDATE
            """,
            (
                incident_id,
                agency_id,
            ),
        )
        .fetchone()
    )

    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "사건이 없거나 "
                "소속 기관에 전달되지 않았습니다."
            ),
        )

    previous_status = (
        recommendation[
            "recommendation_status"
        ]
    )

    # 이미 완료된 요청은 같은 결과를 반환합니다.
    if previous_status == "COMPLETED":
        return {
            "agency_recommendation_id":
                recommendation["id"],
            "agency_id":
                recommendation["agency_id"],
            "recommendation_status":
                "COMPLETED",
        }

    if previous_status != "DELIVERED":
        raise HTTPException(
            status_code=409,
            detail=(
                "전달 완료된 기관 사건만 "
                "대응 완료 처리할 수 있습니다."
            ),
        )

    # RESOLVED인데 아직 DELIVERED가 남아 있다면
    # 정상적인 상태 조합이 아니므로 변경하지 않습니다.
    if incident["status"] == "RESOLVED":
        raise HTTPException(
            status_code=409,
            detail=(
                "이미 종료된 사건의 기관 상태를 "
                "변경할 수 없습니다."
            ),
        )

    # --------------------------------------------------------
    # 3. DELIVERED → COMPLETED
    # --------------------------------------------------------

    completed = (
        connection.execute(
            """
            UPDATE incident_agency_recommendations
            SET recommendation_status = 'COMPLETED'
            WHERE id = %s
              AND recommendation_status = 'DELIVERED'
            RETURNING
                id AS agency_recommendation_id,
                agency_id,
                recommendation_status
            """,
            (
                recommendation["id"],
            ),
        )
        .fetchone()
    )

    if completed is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "기관 대응 완료 상태 변경에 "
                "실패했습니다."
            ),
        )

    return completed



# ------------------------------------------------------------
# LangGraph 추천 결과 저장
# ------------------------------------------------------------

def save_recommendation(
    connection,
    incident_id,
    recommendation,
):
    params = {
        **recommendation,

        "incident_id":
            incident_id,

        "breakdown":
            Jsonb(
                recommendation[
                    "score_breakdown_json"
                ]
            ),
    }

    return connection.execute(
        """
        INSERT INTO
            incident_agency_recommendations (
                incident_id,
                agency_id,
                recommendation_rank,
                recommendation_score,
                score_breakdown_json,
                rule_version
            )

        VALUES (
            %(incident_id)s,
            %(agency_id)s,
            %(recommendation_rank)s,
            %(recommendation_score)s,
            %(breakdown)s,
            %(rule_version)s
        )

        ON CONFLICT (
            incident_id,
            agency_id
        )

        DO UPDATE SET
            recommendation_rank =
                EXCLUDED.recommendation_rank,

            recommendation_score =
                EXCLUDED.recommendation_score,

            score_breakdown_json =
                EXCLUDED.score_breakdown_json,

            rule_version =
                EXCLUDED.rule_version

        RETURNING *
        """,
        params,
    ).fetchone()


def list_analysis_agencies(
    connection,
):
    return connection.execute(
        """
        SELECT *
        FROM agencies
        ORDER BY id
        """
    ).fetchall()


# ------------------------------------------------------------
# 전달용 잠금 / 검증
# ------------------------------------------------------------

def _lock_deliverable_incident(
    connection: Any,
    incident_id: int,
) -> dict:
    """
    사건을 잠그고 전달 가능한 상태인지 검사한다.
    """

    incident = (
        connection.execute(
            """
            SELECT
                id,
                status

            FROM incidents

            WHERE id = %s

            FOR UPDATE
            """,
            (
                incident_id,
            ),
        )
        .fetchone()
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="사건이 없습니다.",
        )

    if (
        incident["status"]
        not in (
            "CONFIRMED",
            "SENT",
        )
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "확인된 사건만 "
                "전달할 수 있습니다."
            ),
        )

    return incident


def _lock_recommendation(
    connection: Any,
    incident_id: int,
    agency_id: int,
) -> dict:
    """
    해당 기관이 사건의 추천 기관인지 확인하고 잠근다.
    """

    recommendation = (
        connection.execute(
            """
            SELECT
                id,
                agency_id,
                recommendation_status

            FROM incident_agency_recommendations

            WHERE incident_id = %s
              AND agency_id = %s

            FOR UPDATE
            """,
            (
                incident_id,
                agency_id,
            ),
        )
        .fetchone()
    )

    if recommendation is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "해당 사건의 "
                "추천 기관이 아닙니다."
            ),
        )

    return recommendation


def _validate_optional_route(
    connection: Any,
    recommendation_id: int,
    route_candidate_id: int | None,
) -> None:
    """
    선택한 경로가 해당 기관의
    유효한 경로 후보인지 검사한다.
    """

    if (
        route_candidate_id
        is None
    ):
        return

    route = (
        connection.execute(
            """
            SELECT
                id

            FROM route_candidates

            WHERE id = %s
              AND agency_recommendation_id = %s
              AND disqualify_reason IS NULL

            FOR SHARE
            """,
            (
                route_candidate_id,
                recommendation_id,
            ),
        )
        .fetchone()
    )

    if route is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "해당 기관에 속한 "
                "제외되지 않은 경로 후보를 "
                "선택하세요."
            ),
        )


# ------------------------------------------------------------
# DB 알림 생성
# ------------------------------------------------------------

def _create_delivery_notifications(
    connection: Any,
    incident_id: int,
    recommendation: dict,
) -> list[dict]:
    """
    새로 전달된 기관의 활성 기관 담당자와
    현장 담당자에게 DB 알림을 생성한다.
    """

    return connection.execute(
        """
        INSERT INTO notifications (
            incidents_id,
            agency_id,
            user_id,
            agency_recommendation_id
        )

        SELECT
            %s,
            %s,
            u.id,
            %s

        FROM users AS u

        WHERE u.agency_id = %s
          AND u.is_active = TRUE
          AND u.role IN (
              'AGENCY_STAFF',
              'RESPONDER'
          )

        ORDER BY
            u.id

        ON CONFLICT (
            agency_recommendation_id,
            user_id
        )
        DO NOTHING

        RETURNING
            id,
            user_id
        """,
        (
            incident_id,
            recommendation[
                "agency_id"
            ],
            recommendation[
                "id"
            ],
            recommendation[
                "agency_id"
            ],
        ),
    ).fetchall()