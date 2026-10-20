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


# =========================================================
# Helpers
# =========================================================


def make_frame(
    seconds: int,
) -> Frame:

    return Frame(
        cctv_id=1,
        captured_at=(
            datetime(
                2026,
                10,
                20,
                10,
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
        hazard_type=hazard_type,
        confidence=confidence,
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
        candidate_confidence_threshold=0.35,
        min_area_ratio=0.0,
        candidate_min_detection_count=3,
        temporal_validation_sec=15.0,
        incident_confidence_threshold=0.35,
        track_ttl_sec=60.0,
        jpeg_quality=90,
    )


# =========================================================
# TEST 1
# 15초 안에 3회 → 즉시 사건 후보
# =========================================================


def test_verify_success() -> None:

    print()
    print(
        "[VERIFY SUCCESS TEST]"
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

    # t=0 : O → 1회
    result = verifier.observe(
        frame=make_frame(0),
        detections_by_hazard={
            "flood": flood,
        },
    )

    if result:
        raise AssertionError(
            "1회 탐지에서 Candidate가 "
            "생성되면 안 됩니다."
        )

    if (
        verifier.pending_hazards(1)
        != ("flood",)
    ):
        raise AssertionError(
            "첫 후보 탐지 후 flood가 "
            "pending 상태여야 합니다."
        )

    # t=2 : X
    result = verifier.observe(
        frame=make_frame(2),
        detections_by_hazard={},
    )

    if result:
        raise AssertionError(
            "미탐 Frame에서 Candidate가 "
            "생성되면 안 됩니다."
        )

    # t=4 : O → 2회
    result = verifier.observe(
        frame=make_frame(4),
        detections_by_hazard={
            "flood": flood,
        },
    )

    if result:
        raise AssertionError(
            "2회 탐지에서 Candidate가 "
            "생성되면 안 됩니다."
        )

    # t=6 : X
    verifier.observe(
        frame=make_frame(6),
        detections_by_hazard={},
    )

    # t=8 : O → 3회
    result = verifier.observe(
        frame=make_frame(8),
        detections_by_hazard={
            "flood": flood,
        },
    )

    if len(result) != 1:
        raise AssertionError(
            "15초 안에 동일 hazard가 "
            "3회 탐지되었는데 Candidate가 "
            "생성되지 않았습니다."
        )

    if (
        result[0].duration_sec
        != 8
    ):
        raise AssertionError(
            "duration이 8초가 아닙니다. "
            f"actual="
            f"{result[0].duration_sec}"
        )

    print(
        "[PASS] "
        "0s / 4s / 8s 탐지 "
        "→ 8초에 즉시 검증 성공"
    )


# =========================================================
# TEST 2
# 15초 초과 → 기존 VERIFY 세션 실패
# 현재 탐지는 새 세션의 1회째
# =========================================================

def test_verify_timeout_and_restart() -> None:

    print()
    print(
        "[VERIFY TIMEOUT TEST]"
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

    # =====================================================
    # 첫 VERIFY 세션
    #
    # t=0   O → 1회
    # t=6   O → 2회
    # t=16  O
    #
    # 최초 후보로부터 16초 경과.
    #
    # 기존 VERIFY 세션은 여기서 무조건 실패한다.
    # 현재 t=16 Detection을 이용해
    # 즉시 새 VERIFY 세션을 시작하면 안 된다.
    # =====================================================

    verifier.observe(
        frame=make_frame(0),
        detections_by_hazard={
            "flood": flood,
        },
    )

    verifier.observe(
        frame=make_frame(6),
        detections_by_hazard={
            "flood": flood,
        },
    )

    result = verifier.observe(
        frame=make_frame(16),
        detections_by_hazard={
            "flood": flood,
        },
    )

    if result:
        raise AssertionError(
            "15초를 초과한 VERIFY 세션에서 "
            "Incident Candidate가 생성되면 "
            "안 됩니다."
        )

    if verifier.pending_hazards(1):
        raise AssertionError(
            "VERIFY timeout 이후에는 "
            "pending hazard가 없어야 합니다."
        )

    print(
        "[PASS] "
        "15초 초과 → 기존 VERIFY 세션 종료"
    )

    # =====================================================
    # 다음 Frame부터 새로운 후보로 시작
    #
    # Runtime에서는 위 timeout 결과를 받고
    # 먼저 BASE / ALERT로 복귀한다.
    #
    # 이후 다시 들어온 Detection부터
    # 새로운 VERIFY 세션이 시작된다.
    #
    # t=18 O → 새 세션 1회
    # t=20 O → 2회
    # t=22 O → 3회 → 사건 후보
    # =====================================================

    result = verifier.observe(
        frame=make_frame(18),
        detections_by_hazard={
            "flood": flood,
        },
    )

    if result:
        raise AssertionError(
            "새 VERIFY 세션 첫 탐지에서 "
            "사건화하면 안 됩니다."
        )

    if (
        verifier.pending_hazards(1)
        != ("flood",)
    ):
        raise AssertionError(
            "timeout 이후 다음 Detection이 "
            "새 VERIFY 후보가 되어야 합니다."
        )

    result = verifier.observe(
        frame=make_frame(20),
        detections_by_hazard={
            "flood": flood,
        },
    )

    if result:
        raise AssertionError(
            "새 VERIFY 세션 2회째에서 "
            "사건화하면 안 됩니다."
        )

    result = verifier.observe(
        frame=make_frame(22),
        detections_by_hazard={
            "flood": flood,
        },
    )

    if len(result) != 1:
        raise AssertionError(
            "새 VERIFY 세션에서 "
            "3회 탐지됐는데 사건화되지 않았습니다."
        )

    if (
        result[0].duration_sec
        != 4
    ):
        raise AssertionError(
            "새 VERIFY 세션 duration은 "
            "18초→22초 = 4초여야 합니다. "
            f"actual="
            f"{result[0].duration_sec}"
        )

    print(
        "[PASS] "
        "복귀 이후 다음 Detection부터 "
        "새 VERIFY 세션 시작"
    )


# =========================================================
# TEST 3
# Incident confidence
# =========================================================


def test_incident_confidence() -> None:

    print()
    print(
        "[INCIDENT CONFIDENCE TEST]"
    )

    config = (
        IncidentPipelineConfig(
            candidate_confidence_threshold=0.35,
            min_area_ratio=0.0,
            candidate_min_detection_count=3,
            temporal_validation_sec=15.0,
            incident_confidence_threshold=0.70,
            track_ttl_sec=60.0,
            jpeg_quality=90,
        )
    )

    verifier = (
        TemporalIncidentVerifier(
            config=config
        )
    )

    # 후보 threshold는 넘지만
    # 사건 확정 threshold는 넘지 못함.

    for seconds, confidence in (
        (0, 0.50),
        (4, 0.55),
        (8, 0.60),
    ):

        result = verifier.observe(
            frame=make_frame(
                seconds
            ),
            detections_by_hazard={
                "flood":
                    make_detection(
                        "flood",
                        confidence,
                    ),
            },
        )

    if result:
        raise AssertionError(
            "Incident confidence 0.70을 "
            "넘지 않았는데 사건화했습니다."
        )

    # 검증 시간은 아직 15초 안.
    # 4번째 Detection이 0.80이면 사건화.

    result = verifier.observe(
        frame=make_frame(10),
        detections_by_hazard={
            "flood":
                make_detection(
                    "flood",
                    0.80,
                ),
        },
    )

    if len(result) != 1:
        raise AssertionError(
            "Incident confidence를 "
            "충족했는데 사건화되지 않았습니다."
        )

    print(
        "[PASS] "
        "반복 탐지 횟수와 "
        "Incident confidence 분리 정상"
    )


# =========================================================
# TEST 4
# 실제 IncidentPipeline 등록 성공
# =========================================================


def test_pipeline_registration() -> None:

    print()
    print(
        "[PIPELINE REGISTRATION TEST]"
    )

    saved_payloads: list[
        dict
    ] = []

    def fake_register(
        payload: dict,
    ) -> dict:

        saved_payloads.append(
            payload.copy()
        )

        return {
            "id": 100,
            "incident_no":
                "TEST-INCIDENT-100",
        }

    pipeline = (
        IncidentPipeline(
            config=make_config(),
            register_fn=fake_register,
        )
    )

    performance = (
        YoloPerformance(
            queue_wait_sec=0.0,
            inference_sec=0.1,
            total_latency_sec=0.1,
        )
    )

    # 0초 → 1회
    result = pipeline.handle_result(
        frame=make_frame(0),
        detections=[
            make_detection(
                "flood",
                0.80,
            )
        ],
        performance=performance,
    )

    if (
        result.pending_hazards
        != ("flood",)
    ):
        raise AssertionError(
            "첫 후보 탐지 후 "
            "pending_hazards에 flood가 "
            "있어야 합니다."
        )

    if saved_payloads:
        raise AssertionError(
            "첫 탐지에서 Incident가 "
            "저장되면 안 됩니다."
        )

    # 4초 → 2회
    pipeline.handle_result(
        frame=make_frame(4),
        detections=[
            make_detection(
                "flood",
                0.76,
            )
        ],
        performance=performance,
    )

    if saved_payloads:
        raise AssertionError(
            "2회 탐지에서 Incident가 "
            "저장되면 안 됩니다."
        )

    # 8초 → 3회 → 저장 성공
    result = pipeline.handle_result(
        frame=make_frame(8),
        detections=[
            make_detection(
                "flood",
                0.75,
            )
        ],
        performance=performance,
    )

    if (
        len(saved_payloads)
        != 1
    ):
        raise AssertionError(
            "3회 탐지 후 Incident가 "
            "1건 저장되어야 합니다."
        )

    if result.pending_hazards:
        raise AssertionError(
            "Incident 저장 성공 후 "
            "pending_hazards가 비어야 합니다."
        )

    if (
        result.registered_hazards
        != ("flood",)
    ):
        raise AssertionError(
            "registered_hazards가 "
            "flood여야 합니다."
        )

    payload = (
        saved_payloads[0]
    )

    if (
        payload["dedup_key"]
        != "cctv:1:hazard:flood"
    ):
        raise AssertionError(
            "dedup_key가 잘못되었습니다."
        )

    if (
        not payload[
            "representative_image"
        ].startswith(
            b"\xff\xd8"
        )
    ):
        raise AssertionError(
            "대표 이미지가 JPEG가 아닙니다."
        )

    print(
        "[PASS] "
        "VERIFY 성공 → Incident 저장 "
        "→ pending 종료"
    )

    # 이미 검증된 재난이 계속 보이면
    # 재검증 없이 동일 dedup_key로 갱신 요청.

    result = pipeline.handle_result(
        frame=make_frame(10),
        detections=[
            make_detection(
                "flood",
                0.82,
            )
        ],
        performance=performance,
    )

    if (
        len(saved_payloads)
        != 2
    ):
        raise AssertionError(
            "지속 탐지가 기존 Incident "
            "갱신 요청으로 이어지지 않았습니다."
        )

    if (
        saved_payloads[1][
            "dedup_key"
        ]
        != payload[
            "dedup_key"
        ]
    ):
        raise AssertionError(
            "지속 탐지 시 dedup_key가 "
            "바뀌었습니다."
        )

    print(
        "[PASS] "
        "검증된 위험 지속 탐지 "
        "→ 같은 dedup_key로 갱신"
    )


# =========================================================
# TEST 5
# Incident DB 저장 실패 시 VERIFY 유지
# =========================================================


def test_registration_failure_keeps_pending() -> None:

    print()
    print(
        "[REGISTRATION FAILURE TEST]"
    )

    should_fail = {
        "value": True,
    }

    saved_payloads: list[
        dict
    ] = []

    def fake_register(
        payload: dict,
    ) -> dict:

        if should_fail["value"]:
            raise RuntimeError(
                "TEST_ONLY_DB_FAILURE"
            )

        saved_payloads.append(
            payload.copy()
        )

        return {
            "id": 200,
            "incident_no":
                "TEST-INCIDENT-200",
        }

    pipeline = (
        IncidentPipeline(
            config=make_config(),
            register_fn=fake_register,
        )
    )

    performance = (
        YoloPerformance(
            queue_wait_sec=0.0,
            inference_sec=0.1,
            total_latency_sec=0.1,
        )
    )

    for seconds in (
        0,
        4,
    ):

        pipeline.handle_result(
            frame=make_frame(
                seconds
            ),
            detections=[
                make_detection(
                    "flood",
                    0.80,
                )
            ],
            performance=performance,
        )

    # 3번째 Detection에서
    # Temporal 검증은 성공하지만
    # DB 저장은 실패.
    result = pipeline.handle_result(
        frame=make_frame(8),
        detections=[
            make_detection(
                "flood",
                0.80,
            )
        ],
        performance=performance,
    )

    if (
        result.pending_hazards
        != ("flood",)
    ):
        raise AssertionError(
            "Incident 저장 실패 시 "
            "VERIFY pending 상태를 "
            "유지해야 합니다."
        )

    if result.registered_hazards:
        raise AssertionError(
            "저장 실패인데 "
            "registered_hazards가 있으면 "
            "안 됩니다."
        )

    print(
        "[PASS] "
        "Incident 저장 실패 "
        "→ VERIFY 유지"
    )

    # 다음 Frame에서 DB 복구.
    should_fail[
        "value"
    ] = False

    result = pipeline.handle_result(
        frame=make_frame(10),
        detections=[
            make_detection(
                "flood",
                0.81,
            )
        ],
        performance=performance,
    )

    if (
        len(saved_payloads)
        != 1
    ):
        raise AssertionError(
            "DB 복구 후 Incident 저장이 "
            "재시도되지 않았습니다."
        )

    if result.pending_hazards:
        raise AssertionError(
            "저장 성공 후 pending 상태가 "
            "종료되지 않았습니다."
        )

    print(
        "[PASS] "
        "다음 Detection에서 저장 재시도 "
        "→ 성공 후 VERIFY 종료"
    )


# =========================================================
# TEST 6
# candidate confidence / 일반 Class 제외
# =========================================================


def test_candidate_filter() -> None:

    print()
    print(
        "[CANDIDATE FILTER TEST]"
    )

    verifier = (
        TemporalIncidentVerifier(
            config=make_config()
        )
    )

    # Verifier 앞의 Filter 자체는
    # IncidentPipeline을 통해 확인한다.

    saved_payloads: list[
        dict
    ] = []

    def fake_register(
        payload: dict,
    ) -> dict:

        saved_payloads.append(
            payload.copy()
        )

        return {
            "id": 300,
            "incident_no":
                "TEST-INCIDENT-300",
        }

    pipeline = (
        IncidentPipeline(
            config=make_config(),
            register_fn=fake_register,
        )
    )

    performance = (
        YoloPerformance(
            queue_wait_sec=0.0,
            inference_sec=0.1,
            total_latency_sec=0.1,
        )
    )

    # 낮은 confidence
    result = pipeline.handle_result(
        frame=make_frame(0),
        detections=[
            make_detection(
                "fallen_tree",
                0.20,
            )
        ],
        performance=performance,
    )

    if result.pending_hazards:
        raise AssertionError(
            "0.20 confidence가 "
            "후보 Track에 들어가면 안 됩니다."
        )

    # 일반 객체
    result = pipeline.handle_result(
        frame=make_frame(2),
        detections=[
            make_detection(
                "car",
                0.99,
            )
        ],
        performance=performance,
    )

    if result.pending_hazards:
        raise AssertionError(
            "car가 재난 후보 Track에 "
            "들어가면 안 됩니다."
        )

    if saved_payloads:
        raise AssertionError(
            "후보 제외 Detection으로 "
            "Incident가 저장됐습니다."
        )

    print(
        "[PASS] "
        "낮은 confidence / 일반 Class 제외"
    )


# =========================================================
# Main
# =========================================================


def main() -> None:

    print(
        "=" * 72
    )

    print(
        "OCTV INCIDENT PIPELINE "
        "15s VERIFY SESSION TEST"
    )

    print(
        "=" * 72
    )

    test_verify_success()

    test_verify_timeout_and_restart()

    test_incident_confidence()

    test_pipeline_registration()

    test_registration_failure_keeps_pending()

    test_candidate_filter()

    print()
    print(
        "=" * 72
    )

    print(
        "[SUCCESS] "
        "후보 탐지 "
        "→ 최대 15초 VERIFY "
        "→ 3회 탐지 "
        "→ Incident 저장 "
        "→ 지속 탐지 갱신 "
        "정상"
    )

    print(
        "=" * 72
    )


if __name__ == "__main__":

    main()