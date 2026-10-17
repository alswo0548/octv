from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)

import numpy as np

from ai.contracts import (
    Detection,
    Frame,
)
from ai.detection.incident_pipeline import (
    IncidentPipeline,
    IncidentPipelineConfig,
    TemporalIncidentVerifier,
)
from ai.detection.yolo_worker import (
    YoloPerformance,
)


KST = timezone(
    timedelta(
        hours=9
    )
)


def make_frame(
    seconds: int,
) -> Frame:

    return Frame(
        cctv_id=1,
        captured_at=(
            datetime(
                2026,
                10,
                14,
                12,
                0,
                0,
                tzinfo=KST,
            )
            + timedelta(
                seconds=seconds
            )
        ),
        image=np.zeros(
            (
                100,
                100,
                3,
            ),
            dtype=np.uint8,
        ),
    )


def make_detection(
    hazard_type: str,
    confidence: float,
) -> Detection:

    return Detection(
        hazard_type=(
            hazard_type
        ),
        confidence=(
            confidence
        ),
        bbox=(
            10.0,
            10.0,
            80.0,
            80.0,
        ),
        model_version=(
            "test-model-v1"
        ),
    )


def make_config() -> IncidentPipelineConfig:

    return IncidentPipelineConfig(
        min_confidence=0.35,
        min_area_ratio=0.0,
        temporal_window_size=5,
        temporal_min_hits=3,
        track_ttl_sec=60.0,
        jpeg_quality=90,
    )


def test_duration() -> None:

    print()
    print(
        "[DURATION TEST]"
    )

    verifier = (
        TemporalIncidentVerifier(
            config=make_config()
        )
    )

    flood = (
        make_detection(
            "flood",
            0.80,
        )
    )

    # O X O X O
    # 20초 시점에 3/5 충족

    verifier.observe(
        frame=make_frame(
            0
        ),
        detections_by_hazard={
            "flood": flood,
        },
    )

    verifier.observe(
        frame=make_frame(
            5
        ),
        detections_by_hazard={},
    )

    verifier.observe(
        frame=make_frame(
            10
        ),
        detections_by_hazard={
            "flood": flood,
        },
    )

    verifier.observe(
        frame=make_frame(
            15
        ),
        detections_by_hazard={},
    )

    first_verified = (
        verifier.observe(
            frame=make_frame(
                20
            ),
            detections_by_hazard={
                "flood": flood,
            },
        )
    )

    if len(first_verified) != 1:

        raise AssertionError(
            "3/5 조건에서 "
            "Candidate가 생성되지 않았습니다."
        )

    if (
        first_verified[
            0
        ].duration_sec
        != 20
    ):

        raise AssertionError(
            "최초 검증 duration이 "
            "20초가 아닙니다. "
            f"actual="
            f"{first_verified[0].duration_sec}"
        )

    print(
        "[PASS] 최초 검증 duration=20s"
    )

    # 다음 Frame도 positive.
    #
    # 기존 구현에서는 Sliding Window의
    # 첫 positive가 바뀌면서 15초로 감소했다.
    #
    # 수정 후에는 최초 positive 시각을
    # 유지하므로 25초가 되어야 한다.

    second_verified = (
        verifier.observe(
            frame=make_frame(
                25
            ),
            detections_by_hazard={
                "flood": flood,
            },
        )
    )

    if len(second_verified) != 1:

        raise AssertionError(
            "지속 탐지에서 "
            "Candidate가 생성되지 않았습니다."
        )

    if (
        second_verified[
            0
        ].duration_sec
        != 25
    ):

        raise AssertionError(
            "지속 탐지 duration이 "
            "25초가 아닙니다. "
            f"actual="
            f"{second_verified[0].duration_sec}"
        )

    print(
        "[PASS] 지속 탐지 duration=25s"
    )

    if (
        second_verified[
            0
        ].duration_sec
        < first_verified[
            0
        ].duration_sec
    ):

        raise AssertionError(
            "duration이 감소했습니다."
        )

    print(
        "[PASS] duration 감소 없음"
    )


def main() -> None:

    print(
        "=" * 70
    )

    print(
        "OCTV INCIDENT PIPELINE TEST"
    )

    print(
        "=" * 70
    )

    saved_candidates: list[
        dict
    ] = []

    def fake_register(
        payload: dict,
    ) -> dict:

        saved_candidates.append(
            payload.copy()
        )

        return {
            "id":
                len(
                    saved_candidates
                ),

            "incident_no":
                (
                    "TEST-"
                    f"{len(saved_candidates)}"
                ),
        }

    pipeline = IncidentPipeline(
        config=make_config(),
        register_fn=(
            fake_register
        ),
    )

    performance = (
        YoloPerformance(
            queue_wait_sec=0.0,
            inference_sec=0.1,
            total_latency_sec=0.1,
        )
    )

    # =====================================================
    # TEST 1
    # Frame 1
    # =====================================================

    print()
    print(
        "[TEST 1] Frame 1 / flood 탐지"
    )

    pipeline.handle_result(
        frame=make_frame(
            0
        ),
        detections=[
            make_detection(
                "flood",
                0.80,
            )
        ],
        performance=performance,
    )

    if saved_candidates:

        raise AssertionError(
            "첫 탐지 1회만으로 "
            "Incident가 생성됐습니다."
        )

    print(
        "[PASS] 1/1 → 사건 생성 안 함"
    )

    # =====================================================
    # TEST 2
    # =====================================================

    print()
    print(
        "[TEST 2] Frame 2 / flood 미탐"
    )

    pipeline.handle_result(
        frame=make_frame(
            5
        ),
        detections=[],
        performance=performance,
    )

    if saved_candidates:

        raise AssertionError(
            "미탐 Frame에서 "
            "Incident가 생성됐습니다."
        )

    print(
        "[PASS] 1/2 → 사건 생성 안 함"
    )

    # =====================================================
    # TEST 3
    # =====================================================

    print()
    print(
        "[TEST 3] Frame 3 / flood 두 번째 탐지"
    )

    pipeline.handle_result(
        frame=make_frame(
            10
        ),
        detections=[
            make_detection(
                "flood",
                0.76,
            )
        ],
        performance=performance,
    )

    if saved_candidates:

        raise AssertionError(
            "2회 탐지만으로 "
            "Incident가 생성됐습니다."
        )

    print(
        "[PASS] 2/3 → 사건 생성 안 함"
    )

    # =====================================================
    # TEST 4
    # =====================================================

    print()
    print(
        "[TEST 4] Frame 4 / flood 미탐"
    )

    pipeline.handle_result(
        frame=make_frame(
            15
        ),
        detections=[],
        performance=performance,
    )

    if saved_candidates:

        raise AssertionError(
            "최근 4 Frame 중 "
            "2회 탐지 상태에서 "
            "Incident가 생성됐습니다."
        )

    print(
        "[PASS] 2/4 → 사건 생성 안 함"
    )

    # =====================================================
    # TEST 5
    # O X O X O
    # → 3/5
    # =====================================================

    print()
    print(
        "[TEST 5] Frame 5 / 3-of-5 충족"
    )

    pipeline.handle_result(
        frame=make_frame(
            20
        ),
        detections=[
            make_detection(
                "flood",
                0.75,
            )
        ],
        performance=performance,
    )

    if (
        len(
            saved_candidates
        )
        != 1
    ):

        raise AssertionError(
            "최근 5 Frame 중 "
            "3회 탐지 조건에서 "
            "Incident가 생성되지 않았습니다."
        )

    first = (
        saved_candidates[
            0
        ]
    )

    if (
        first[
            "dedup_key"
        ]
        != "cctv:1:hazard:flood"
    ):

        raise AssertionError(
            "dedup_key가 "
            "예상과 다릅니다. "
            f"actual="
            f"{first['dedup_key']}"
        )

    if (
        not first[
            "representative_image"
        ].startswith(
            b"\xff\xd8"
        )
    ):

        raise AssertionError(
            "대표 이미지가 "
            "JPEG 형식이 아닙니다."
        )

    print(
        "[PASS] 3/5 Temporal "
        "→ Incident 생성"
    )

    print(
        "[PASS] JPEG 대표 이미지 생성"
    )

    print(
        "[PASS] dedup_key 유지"
    )

    # =====================================================
    # TEST 6
    # 지속 탐지
    # =====================================================

    print()
    print(
        "[TEST 6] 지속 탐지"
    )

    pipeline.handle_result(
        frame=make_frame(
            25
        ),
        detections=[
            make_detection(
                "flood",
                0.82,
            )
        ],
        performance=performance,
    )

    if (
        len(
            saved_candidates
        )
        != 2
    ):

        raise AssertionError(
            "지속 탐지가 기존 사건 "
            "UPSERT 요청으로 연결되지 않았습니다."
        )

    if (
        saved_candidates[
            1
        ][
            "dedup_key"
        ]
        != first[
            "dedup_key"
        ]
    ):

        raise AssertionError(
            "지속 탐지의 dedup_key가 "
            "변경됐습니다."
        )

    print(
        "[PASS] 지속 탐지 "
        "→ 같은 dedup_key"
    )

    # =====================================================
    # TEST 7
    # 낮은 confidence
    # =====================================================

    print()
    print(
        "[TEST 7] 낮은 confidence"
    )

    before_count = len(
        saved_candidates
    )

    pipeline.handle_result(
        frame=make_frame(
            30
        ),
        detections=[
            make_detection(
                "fallen_tree",
                0.20,
            )
        ],
        performance=performance,
    )

    if (
        len(
            saved_candidates
        )
        != before_count
    ):

        raise AssertionError(
            "낮은 confidence Detection이 "
            "사건 후보로 처리됐습니다."
        )

    print(
        "[PASS] 낮은 confidence 제외"
    )

    # =====================================================
    # TEST 8
    # 일반 객체 제외
    # =====================================================

    print()
    print(
        "[TEST 8] 일반 객체 Class"
    )

    pipeline.handle_result(
        frame=make_frame(
            35
        ),
        detections=[
            make_detection(
                "car",
                0.99,
            )
        ],
        performance=performance,
    )

    if (
        len(
            saved_candidates
        )
        != before_count
    ):

        raise AssertionError(
            "일반 객체 Class가 "
            "Incident로 처리됐습니다."
        )

    print(
        "[PASS] car 등 일반 Class 제외"
    )

    # =====================================================
    # duration 직접 검증
    # =====================================================

    test_duration()

    print()
    print(
        "=" * 70
    )

    print(
        "[SUCCESS] "
        "후보 Filter → "
        "3-of-5 Temporal Verification "
        "→ Duration → "
        "Incident Payload → JPEG "
        "Pipeline 정상"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":

    main()