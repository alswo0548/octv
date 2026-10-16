from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import uuid4

from fastapi import HTTPException

from backend.app.db.session import (
    get_connection,
)
from backend.app.incidents import (
    repository,
    service,
)


KST = timezone(
    timedelta(
        hours=9
    )
)


def get_test_cctv_id() -> int:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id
            FROM cctvs
            ORDER BY id
            LIMIT 1;
            """
        ).fetchone()

    if row is None:
        raise RuntimeError(
            "테스트에 사용할 CCTV가 없습니다."
        )

    return int(
        row["id"]
    )


def count_incidents(
    dedup_key: str,
) -> int:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM incidents
            WHERE dedup_key = %s;
            """,
            (
                dedup_key,
            ),
        ).fetchone()

    return int(
        row["n"]
    )


def find_latest(
    dedup_key: str,
):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                id,
                incident_no,
                status,
                detected_at,
                last_detected_at
            FROM incidents
            WHERE dedup_key = %s
            ORDER BY id DESC
            LIMIT 1;
            """,
            (
                dedup_key,
            ),
        ).fetchone()


def cleanup(
    dedup_key: str,
) -> None:
    with get_connection() as connection:
        rows = connection.execute(
            """
            DELETE FROM incidents
            WHERE dedup_key = %s
            RETURNING id;
            """,
            (
                dedup_key,
            ),
        ).fetchall()

    print(
        "[CLEANUP] "
        f"삭제된 테스트 Incident={len(rows)}"
    )


def detection_payload(
    *,
    cctv_id: int,
    dedup_key: str,
    detected_at: datetime,
    confidence: float,
) -> dict:
    return {
        "cctv_id":
            cctv_id,
        "hazard_type":
            "road_obstacle",
        "confidence":
            confidence,
        "model_version":
            "workflow-test-v1",
        "detection_bbox_json":
            {
                "x1": 10.0,
                "y1": 20.0,
                "x2": 100.0,
                "y2": 110.0,
            },
        "dedup_key":
            dedup_key,
        "detected_at":
            detected_at,
        "representative_image":
            b"\xff\xd8workflow-test\xff\xd9",
    }


def main() -> None:
    print(
        "=" * 72
    )
    print(
        "OCTV INCIDENT WORKFLOW DB INTEGRATION TEST"
    )
    print(
        "=" * 72
    )

    cctv_id = (
        get_test_cctv_id()
    )

    dedup_key = (
        "test:incident-workflow:"
        + uuid4().hex
    )

    admin = {
        "id": -1,
        "role":
            "CONTROL_ADMIN",
        "agency_id":
            None,
    }

    responder = {
        "id": -2,
        "role":
            "RESPONDER",
        "agency_id":
            1,
    }

    first_at = datetime.now(
        KST
    )

    try:
        # ====================================================
        # TEST 1
        # 새 사건 → DETECTED
        # ====================================================

        print()
        print(
            "[TEST 1] 새 Incident 생성"
        )

        first = (
            service.register_detection(
                detection_payload(
                    cctv_id=cctv_id,
                    dedup_key=dedup_key,
                    detected_at=first_at,
                    confidence=0.81,
                )
            )
        )

        first_id = int(
            first["id"]
        )

        if (
            first["status"]
            != "DETECTED"
        ):
            raise AssertionError(
                "새 사건 상태가 DETECTED가 아닙니다."
            )

        print(
            "[PASS] "
            f"incident_id={first_id} "
            "/ status=DETECTED"
        )

        # ====================================================
        # TEST 2
        # 비관리자 변경 차단
        # ====================================================

        print()
        print(
            "[TEST 2] 비관리자 상태 변경 차단"
        )

        try:
            service.confirm_incident(
                first_id,
                responder,
            )
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
        else:
            raise AssertionError(
                "비관리자가 사건 상태를 변경했습니다."
            )

        print(
            "[PASS] RESPONDER → 403"
        )

        # ====================================================
        # TEST 3
        # DETECTED → CONFIRMED
        # ====================================================

        print()
        print(
            "[TEST 3] 사건 확인"
        )

        confirmed = (
            service.confirm_incident(
                first_id,
                admin,
            )
        )

        if (
            confirmed["status"]
            != "CONFIRMED"
        ):
            raise AssertionError(
                "DETECTED → CONFIRMED 전환 실패"
            )

        print(
            "[PASS] DETECTED → CONFIRMED"
        )

        # ====================================================
        # TEST 4
        # CONFIRMED → FALSE_POSITIVE
        # ====================================================

        print()
        print(
            "[TEST 4] 오탐 처리"
        )

        false_positive = (
            service.mark_false_positive(
                first_id,
                admin,
            )
        )

        if (
            false_positive["status"]
            != "FALSE_POSITIVE"
        ):
            raise AssertionError(
                "FALSE_POSITIVE 전환 실패"
            )

        print(
            "[PASS] "
            "CONFIRMED → FALSE_POSITIVE"
        )

        # ====================================================
        # TEST 5
        # 기본 목록에서 오탐 제외
        # ====================================================

        print()
        print(
            "[TEST 5] 기본 목록 오탐 제외"
        )

        incident_no = (
            false_positive[
                "incident_no"
            ]
        )

        default_page = (
            service.list_incidents(
                page=1,
                page_size=5,
                filters={
                    "q":
                        incident_no,
                },
                user=admin,
            )
        )

        if (
            default_page["total"]
            != 0
        ):
            raise AssertionError(
                "FALSE_POSITIVE 사건이 "
                "기본 목록에 노출됩니다."
            )

        false_positive_page = (
            service.list_incidents(
                page=1,
                page_size=5,
                filters={
                    "q":
                        incident_no,
                    "status":
                        "FALSE_POSITIVE",
                },
                user=admin,
            )
        )

        if (
            false_positive_page["total"]
            != 1
        ):
            raise AssertionError(
                "FALSE_POSITIVE 필터에서 "
                "오탐 사건을 조회할 수 없습니다."
            )

        print(
            "[PASS] 기본 목록 제외"
        )
        print(
            "[PASS] "
            "status=FALSE_POSITIVE 조회 가능"
        )

        # ====================================================
        # TEST 6
        # 오탐 직후 같은 장면 재탐지
        # → 새 Incident 금지
        # ====================================================

        print()
        print(
            "[TEST 6] 오탐 직후 동일 탐지 억제"
        )

        second_at = (
            first_at
            + timedelta(
                seconds=10
            )
        )

        suppressed = (
            service.register_detection(
                detection_payload(
                    cctv_id=cctv_id,
                    dedup_key=dedup_key,
                    detected_at=second_at,
                    confidence=0.88,
                )
            )
        )

        if (
            int(
                suppressed["id"]
            )
            != first_id
        ):
            raise AssertionError(
                "오탐 직후 새 Incident가 생성됐습니다."
            )

        if (
            suppressed["status"]
            != "FALSE_POSITIVE"
        ):
            raise AssertionError(
                "억제 대상 사건 상태가 "
                "FALSE_POSITIVE가 아닙니다."
            )

        if (
            count_incidents(
                dedup_key
            )
            != 1
        ):
            raise AssertionError(
                "오탐 직후 동일 사건이 "
                "중복 생성됐습니다."
            )

        print(
            "[PASS] 동일 오탐 재탐지 억제"
        )
        print(
            "[PASS] Incident 수=1"
        )

        # ====================================================
        # TEST 7
        # 탐지가 60초 이상 끊긴 뒤 다시 발생
        # → 새 DETECTED 허용
        # ====================================================

        print()
        print(
            "[TEST 7] 오탐 재활성화 간격 이후 새 사건"
        )

        third_at = (
            second_at
            + timedelta(
                seconds=61
            )
        )

        third = (
            service.register_detection(
                detection_payload(
                    cctv_id=cctv_id,
                    dedup_key=dedup_key,
                    detected_at=third_at,
                    confidence=0.92,
                )
            )
        )

        third_id = int(
            third["id"]
        )

        if (
            third_id
            == first_id
        ):
            raise AssertionError(
                "재활성화 간격 이후에도 "
                "새 Incident가 생성되지 않았습니다."
            )

        if (
            third["status"]
            != "DETECTED"
        ):
            raise AssertionError(
                "새 Incident가 DETECTED가 아닙니다."
            )

        if (
            count_incidents(
                dedup_key
            )
            != 2
        ):
            raise AssertionError(
                "예상 Incident 수가 2가 아닙니다."
            )

        print(
            "[PASS] 새 DETECTED 생성"
        )

        # ====================================================
        # TEST 8
        # DETECTED → CONFIRMED → SENT
        # ====================================================

        print()
        print(
            "[TEST 8] 기관 전달 완료 상태"
        )

        confirmed_again = (
            service.confirm_incident(
                third_id,
                admin,
            )
        )

        if (
            confirmed_again["status"]
            != "CONFIRMED"
        ):
            raise AssertionError(
                "새 사건 CONFIRMED 전환 실패"
            )

        sent = (
            service.mark_sent(
                third_id,
                admin,
            )
        )

        if (
            sent["status"]
            != "SENT"
        ):
            raise AssertionError(
                "CONFIRMED → SENT 전환 실패"
            )

        print(
            "[PASS] "
            "DETECTED → CONFIRMED → SENT"
        )

        # ====================================================
        # TEST 9
        # SENT 사건 오탐 전환 금지
        # ====================================================

        print()
        print(
            "[TEST 9] SENT → FALSE_POSITIVE 차단"
        )

        try:
            service.mark_false_positive(
                third_id,
                admin,
            )
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
        else:
            raise AssertionError(
                "SENT 사건이 "
                "FALSE_POSITIVE로 변경됐습니다."
            )

        print(
            "[PASS] SENT 오탐 변경 → 409"
        )

        latest = (
            find_latest(
                dedup_key
            )
        )

        if (
            latest is None
            or latest["status"]
            != "SENT"
        ):
            raise AssertionError(
                "최종 사건 상태가 SENT가 아닙니다."
            )

        print()
        print(
            "=" * 72
        )
        print(
            "[SUCCESS] "
            "Incident 상태 흐름 / 오탐 목록 제외 / "
            "오탐 재생성 억제 정상"
        )
        print(
            "=" * 72
        )

    finally:
        print()
        cleanup(
            dedup_key
        )


if __name__ == "__main__":
    main()