from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import uuid4

import cv2
import numpy as np

from backend.app.db.session import (
    get_connection,
)
from backend.app.incidents.service import (
    register_detection,
)


KST = timezone(
    timedelta(hours=9)
)


def make_jpeg(
    value: int,
) -> bytes:

    image = np.full(
        (
            120,
            160,
            3,
        ),
        value,
        dtype=np.uint8,
    )

    success, encoded = cv2.imencode(
        ".jpg",
        image,
    )

    if not success:
        raise RuntimeError(
            "테스트 JPEG 인코딩 실패"
        )

    return encoded.tobytes()


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


def find_test_incident(
    dedup_key: str,
):

    with get_connection() as connection:

        return connection.execute(
            """
            SELECT
                id,
                incident_no,
                cctv_id,
                hazard_type,
                confidence,
                model_version,
                dedup_key,
                status,
                detected_at,
                last_detected_at,
                representative_image,
                representative_image_updated_at
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

        deleted = connection.execute(
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
        f"삭제된 테스트 Incident="
        f"{len(deleted)}"
    )


def main() -> None:

    print(
        "=" * 70
    )
    print(
        "OCTV INCIDENT DB INTEGRATION TEST"
    )
    print(
        "=" * 70
    )

    cctv_id = (
        get_test_cctv_id()
    )

    dedup_key = (
        "test:incident-db:"
        + uuid4().hex
    )

    first_at = datetime.now(
        KST
    )

    second_at = (
        first_at
        + timedelta(
            seconds=10
        )
    )

    first_image = make_jpeg(
        40
    )

    second_image = make_jpeg(
        180
    )

    print(
        f"[SETUP] cctv_id={cctv_id}"
    )

    print(
        f"[SETUP] dedup_key={dedup_key}"
    )

    try:

        # =================================================
        # TEST 1
        # 첫 검증된 Detection
        # → 새 Incident INSERT
        # =================================================

        print()
        print(
            "[TEST 1] 첫 검증 Detection 저장"
        )

        first_result = register_detection(
            {
                "cctv_id":
                    cctv_id,

                "hazard_type":
                    "flood",

                "confidence":
                    0.71,

                "model_version":
                    "integration-test-v1",

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
                    first_at,

                "representative_image":
                    first_image,
            }
        )

        first_id = int(
            first_result["id"]
        )

        print(
            "[INSERT] "
            f"incident_id={first_id} "
            f"/ incident_no="
            f"{first_result['incident_no']}"
        )

        stored_first = (
            find_test_incident(
                dedup_key
            )
        )

        if stored_first is None:
            raise AssertionError(
                "Incident가 DB에 "
                "저장되지 않았습니다."
            )

        if (
            int(
                stored_first["id"]
            )
            != first_id
        ):
            raise AssertionError(
                "DB Incident ID와 "
                "반환 ID가 다릅니다."
            )

        if (
            stored_first["status"]
            != "DETECTED"
        ):
            raise AssertionError(
                "새 사건 상태가 "
                "DETECTED가 아닙니다. "
                f"actual="
                f"{stored_first['status']}"
            )

        if (
            bytes(
                stored_first[
                    "representative_image"
                ]
            )
            != first_image
        ):
            raise AssertionError(
                "첫 대표 이미지가 "
                "정상 저장되지 않았습니다."
            )

        print(
            "[PASS] 새 Incident INSERT"
        )
        print(
            "[PASS] status=DETECTED"
        )
        print(
            "[PASS] 대표 이미지 BYTEA 저장"
        )

        # =================================================
        # TEST 2
        # 같은 CCTV + hazard + dedup_key
        # → 새 Incident 금지
        # → 기존 Incident UPDATE
        # =================================================

        print()
        print(
            "[TEST 2] 같은 사건 재탐지"
        )

        second_result = register_detection(
            {
                "cctv_id":
                    cctv_id,

                "hazard_type":
                    "flood",

                "confidence":
                    0.88,

                "model_version":
                    "integration-test-v1",

                "detection_bbox_json":
                    {
                        "x1": 15.0,
                        "y1": 25.0,
                        "x2": 105.0,
                        "y2": 115.0,
                    },

                "dedup_key":
                    dedup_key,

                "detected_at":
                    second_at,

                "representative_image":
                    second_image,
            }
        )

        second_id = int(
            second_result["id"]
        )

        if second_id != first_id:
            raise AssertionError(
                "같은 active 사건인데 "
                "새 Incident가 생성됐습니다. "
                f"first_id={first_id}, "
                f"second_id={second_id}"
            )

        stored_second = (
            find_test_incident(
                dedup_key
            )
        )

        if stored_second is None:
            raise AssertionError(
                "재탐지 이후 Incident를 "
                "조회할 수 없습니다."
            )

        print(
            "[PASS] 같은 사건 "
            "→ 기존 Incident UPSERT"
        )

        # =================================================
        # TEST 3
        # last_detected_at 갱신
        # =================================================

        print()
        print(
            "[TEST 3] 최근 탐지 시각 갱신"
        )

        if (
            stored_second[
                "last_detected_at"
            ]
            <= stored_second[
                "detected_at"
            ]
        ):
            raise AssertionError(
                "last_detected_at이 "
                "갱신되지 않았습니다."
            )

        print(
            "[PASS] last_detected_at 갱신"
        )

        # =================================================
        # TEST 4
        # 최신 대표 이미지로 교체
        # =================================================

        print()
        print(
            "[TEST 4] 대표 이미지 갱신"
        )

        stored_image = bytes(
            stored_second[
                "representative_image"
            ]
        )

        if stored_image != second_image:
            raise AssertionError(
                "대표 이미지가 "
                "최신 Frame 이미지로 "
                "교체되지 않았습니다."
            )

        print(
            "[PASS] 대표 이미지 최신화"
        )

        # =================================================
        # RESULT
        # =================================================

        print()
        print(
            "=" * 70
        )
        print(
            "[SUCCESS] "
            "Incident DB INSERT "
            "→ Active Incident UPSERT "
            "→ 대표 이미지 갱신 정상"
        )
        print(
            "=" * 70
        )

    finally:

        print()
        print(
            "[FINALIZE] "
            "테스트 데이터 삭제"
        )

        cleanup(
            dedup_key
        )


if __name__ == "__main__":

    main()