from __future__ import annotations

from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
    timezone,
)
import unittest
from unittest.mock import patch

import numpy as np

from ai.contracts import (
    Detection,
    Frame,
)

from ai.detection.cctv_runtime import (
    CctvDetectionRuntime,
    DEFAULT_SAMPLING_CHECK_INTERVAL_SEC,
)

from ai.detection.frame_sampler import (
    FrameSampler,
)

from ai.detection.incident_pipeline import (
    IncidentPipeline,
    IncidentPipelineConfig,
)

from ai.detection.incident_runtime import (
    IncidentAwareCctvDetectionRuntime,
)

from ai.detection.sampling_monitor import (
    SamplingPolicyMonitor,
)

from ai.detection.yolo_worker import (
    YoloPerformance,
)

from backend.app.cctvs import (
    repository as cctv_repository,
)


KST = timezone(
    timedelta(
        hours=9
    )
)


# ============================================================
# Test Helpers
# ============================================================


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
    confidence: float = 0.80,
) -> Detection:

    return Detection(
        hazard_type="flood",
        confidence=confidence,
        bbox=(
            10.0,
            10.0,
            80.0,
            80.0,
        ),
        model_version=(
            "integration-test-model"
        ),
    )


def make_performance() -> YoloPerformance:

    return YoloPerformance(
        queue_wait_sec=0.0,
        inference_sec=0.01,
        total_latency_sec=0.01,
    )


def make_incident_config(
) -> IncidentPipelineConfig:

    return IncidentPipelineConfig(
        candidate_confidence_threshold=0.35,
        min_area_ratio=0.0,
        candidate_min_detection_count=3,
        temporal_validation_sec=15.0,
        incident_confidence_threshold=0.35,
        track_ttl_sec=60.0,
        jpeg_quality=90,
    )


SAMPLING_SETTINGS = {
    "base_analysis_interval_sec": 5.0,
    "alert_analysis_interval_sec": 3.0,
    "verify_analysis_interval_sec": 2.0,
}


# ============================================================
# Fake DB Connection
#
# 실제 Repository의 PostgreSQL 동작은
# 별도 테스트에서 이미 검증했으므로,
# 이번 테스트에서는 Runtime 상태 흐름만 확인한다.
# ============================================================


@contextmanager
def fake_get_connection():

    yield object()


# ============================================================
# Integration Test
# ============================================================


class IncidentRuntimeIntegrationTests(
    unittest.TestCase
):

    # ========================================================
    # Runtime 구성
    # ========================================================

    def make_runtime(
        self,
        initial_mode: str,
    ):

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
                    "TEST-INTEGRATION-100",
            }

        pipeline = (
            IncidentPipeline(
                config=(
                    make_incident_config()
                ),
                register_fn=(
                    fake_register
                ),
            )
        )

        # Runtime 전체 __init__을 실행하면
        # CaptureWorker / YOLO / Thread까지
        # 시작 준비가 필요하므로,
        # 이번 통합 테스트에서는
        # 실제 검증 대상 필드만 주입한다.
        runtime = object.__new__(
            IncidentAwareCctvDetectionRuntime
        )

        runtime._incident_pipeline = (
            pipeline
        )

        runtime._verify_restore_mode_by_cctv = {}

        sampler = (
            FrameSampler(
                default_interval_sec=5.0
            )
        )

        monitor = (
            SamplingPolicyMonitor(
                sampler=sampler,
                check_interval_sec=(
                    DEFAULT_SAMPLING_CHECK_INTERVAL_SEC
                ),
            )
        )

        state = {
            "mode":
                initial_mode,
        }

        # ----------------------------------------------------
        # Fake Repository
        # ----------------------------------------------------

        def enter_verify_mode(
            connection,
            cctv_id: int,
        ):

            current_mode = (
                state[
                    "mode"
                ]
            )

            if current_mode == "VERIFY":

                return {
                    "id":
                        cctv_id,

                    "changed":
                        False,

                    "previous_mode":
                        None,

                    "monitored_mode":
                        "VERIFY",
                }

            if current_mode == "OFF":

                return {
                    "id":
                        cctv_id,

                    "changed":
                        False,

                    "previous_mode":
                        "OFF",

                    "monitored_mode":
                        "OFF",
                }

            previous_mode = (
                current_mode
            )

            state[
                "mode"
            ] = "VERIFY"

            return {
                "id":
                    cctv_id,

                "changed":
                    True,

                "previous_mode":
                    previous_mode,

                "monitored_mode":
                    "VERIFY",
            }

        def restore_from_verify_mode(
            connection,
            cctv_id: int,
            restore_mode: str,
        ):

            if (
                state[
                    "mode"
                ]
                != "VERIFY"
            ):
                return None

            state[
                "mode"
            ] = restore_mode

            return {
                "id":
                    cctv_id,

                "monitored_mode":
                    restore_mode,
            }

        return {
            "runtime":
                runtime,

            "sampler":
                sampler,

            "monitor":
                monitor,

            "state":
                state,

            "saved_payloads":
                saved_payloads,

            "enter_verify_mode":
                enter_verify_mode,

            "restore_from_verify_mode":
                restore_from_verify_mode,
        }

    # ========================================================
    # Sampling Monitor 1회 Poll
    # ========================================================

    @staticmethod
    def apply_sampling(
        monitor: SamplingPolicyMonitor,
        state: dict,
    ) -> None:

        monitor._apply_states(
            states=[
                {
                    "id": 1,
                    "monitored_mode":
                        state[
                            "mode"
                        ],
                }
            ],
            settings=SAMPLING_SETTINGS,
        )

    # ========================================================
    # TEST 1
    #
    # BASE
    # → VERIFY
    # → 2초
    # → Incident
    # → BASE
    # → 5초
    # ========================================================

    def test_base_verify_incident_base_flow(
        self,
    ) -> None:

        context = (
            self.make_runtime(
                initial_mode="BASE"
            )
        )

        runtime = (
            context[
                "runtime"
            ]
        )

        sampler = (
            context[
                "sampler"
            ]
        )

        monitor = (
            context[
                "monitor"
            ]
        )

        state = (
            context[
                "state"
            ]
        )

        saved_payloads = (
            context[
                "saved_payloads"
            ]
        )

        # ----------------------------------------------------
        # 최초 BASE 정책
        # ----------------------------------------------------

        self.apply_sampling(
            monitor,
            state,
        )

        self.assertEqual(
            state[
                "mode"
            ],
            "BASE",
        )

        self.assertEqual(
            sampler.get_interval(
                1
            ),
            5.0,
        )

        with (
            patch(
                "ai.detection.incident_runtime.get_connection",
                new=fake_get_connection,
            ),
            patch.object(
                cctv_repository,
                "enter_verify_mode",
                side_effect=(
                    context[
                        "enter_verify_mode"
                    ]
                ),
            ),
            patch.object(
                cctv_repository,
                "restore_from_verify_mode",
                side_effect=(
                    context[
                        "restore_from_verify_mode"
                    ]
                ),
            ),
            patch.object(
                CctvDetectionRuntime,
                "_handle_yolo_result",
                return_value=None,
            ),
        ):

            # =================================================
            # t=0
            # 첫 위험 후보
            #
            # BASE → VERIFY
            # =================================================

            runtime._handle_yolo_result(
                frame=make_frame(
                    0
                ),
                detections=[
                    make_detection(
                        0.80
                    )
                ],
                performance=(
                    make_performance()
                ),
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "VERIFY",
            )

            self.assertEqual(
                len(
                    saved_payloads
                ),
                0,
            )

            # SamplingPolicyMonitor가
            # 다음 poll에서 VERIFY를 감지.
            self.apply_sampling(
                monitor,
                state,
            )

            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                2.0,
            )

            # =================================================
            # t=2
            # 두 번째 탐지
            #
            # VERIFY 유지
            # =================================================

            runtime._handle_yolo_result(
                frame=make_frame(
                    2
                ),
                detections=[
                    make_detection(
                        0.78
                    )
                ],
                performance=(
                    make_performance()
                ),
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "VERIFY",
            )

            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                2.0,
            )

            self.assertEqual(
                len(
                    saved_payloads
                ),
                0,
            )

            # =================================================
            # t=4
            # 세 번째 탐지
            #
            # Incident 생성
            # VERIFY → BASE
            # =================================================

            runtime._handle_yolo_result(
                frame=make_frame(
                    4
                ),
                detections=[
                    make_detection(
                        0.77
                    )
                ],
                performance=(
                    make_performance()
                ),
            )

            self.assertEqual(
                len(
                    saved_payloads
                ),
                1,
            )

            self.assertEqual(
                saved_payloads[
                    0
                ][
                    "dedup_key"
                ],
                "cctv:1:hazard:flood",
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "BASE",
            )

            # DB mode는 BASE로 돌아왔지만,
            # FrameSampler는 Monitor 다음 poll에서
            # BASE 정책으로 복귀한다.
            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                2.0,
            )

            self.apply_sampling(
                monitor,
                state,
            )

            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                5.0,
            )

        print()
        print(
            "[PASS] "
            "BASE 5s "
            "→ 후보 "
            "→ VERIFY 2s "
            "→ 3회 탐지 "
            "→ Incident "
            "→ BASE 5s"
        )

    # ========================================================
    # TEST 2
    #
    # ALERT
    # → VERIFY
    # → Incident
    # → ALERT
    # ========================================================

    def test_alert_verify_incident_alert_flow(
        self,
    ) -> None:

        context = (
            self.make_runtime(
                initial_mode="ALERT"
            )
        )

        runtime = (
            context[
                "runtime"
            ]
        )

        sampler = (
            context[
                "sampler"
            ]
        )

        monitor = (
            context[
                "monitor"
            ]
        )

        state = (
            context[
                "state"
            ]
        )

        saved_payloads = (
            context[
                "saved_payloads"
            ]
        )

        # ALERT = 3초
        self.apply_sampling(
            monitor,
            state,
        )

        self.assertEqual(
            sampler.get_interval(
                1
            ),
            3.0,
        )

        with (
            patch(
                "ai.detection.incident_runtime.get_connection",
                new=fake_get_connection,
            ),
            patch.object(
                cctv_repository,
                "enter_verify_mode",
                side_effect=(
                    context[
                        "enter_verify_mode"
                    ]
                ),
            ),
            patch.object(
                cctv_repository,
                "restore_from_verify_mode",
                side_effect=(
                    context[
                        "restore_from_verify_mode"
                    ]
                ),
            ),
            patch.object(
                CctvDetectionRuntime,
                "_handle_yolo_result",
                return_value=None,
            ),
        ):

            # 첫 후보
            runtime._handle_yolo_result(
                make_frame(0),
                [
                    make_detection(
                        0.80
                    )
                ],
                make_performance(),
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "VERIFY",
            )

            self.apply_sampling(
                monitor,
                state,
            )

            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                2.0,
            )

            # 2회
            runtime._handle_yolo_result(
                make_frame(2),
                [
                    make_detection(
                        0.79
                    )
                ],
                make_performance(),
            )

            # 3회 → Incident
            runtime._handle_yolo_result(
                make_frame(4),
                [
                    make_detection(
                        0.78
                    )
                ],
                make_performance(),
            )

            self.assertEqual(
                len(
                    saved_payloads
                ),
                1,
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "ALERT",
            )

            self.apply_sampling(
                monitor,
                state,
            )

            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                3.0,
            )

        print()
        print(
            "[PASS] "
            "ALERT 3s "
            "→ VERIFY 2s "
            "→ Incident "
            "→ ALERT 3s"
        )

    # ========================================================
    # TEST 3
    #
    # VERIFY timeout
    # → BASE 복귀
    #
    # 같은 Frame에서 새 VERIFY 연장 금지
    # ========================================================

    def test_verify_timeout_returns_to_base(
        self,
    ) -> None:

        context = (
            self.make_runtime(
                initial_mode="BASE"
            )
        )

        runtime = (
            context[
                "runtime"
            ]
        )

        sampler = (
            context[
                "sampler"
            ]
        )

        monitor = (
            context[
                "monitor"
            ]
        )

        state = (
            context[
                "state"
            ]
        )

        saved_payloads = (
            context[
                "saved_payloads"
            ]
        )

        self.apply_sampling(
            monitor,
            state,
        )

        with (
            patch(
                "ai.detection.incident_runtime.get_connection",
                new=fake_get_connection,
            ),
            patch.object(
                cctv_repository,
                "enter_verify_mode",
                side_effect=(
                    context[
                        "enter_verify_mode"
                    ]
                ),
            ),
            patch.object(
                cctv_repository,
                "restore_from_verify_mode",
                side_effect=(
                    context[
                        "restore_from_verify_mode"
                    ]
                ),
            ),
            patch.object(
                CctvDetectionRuntime,
                "_handle_yolo_result",
                return_value=None,
            ),
        ):

            # t=0 : 1회
            runtime._handle_yolo_result(
                make_frame(0),
                [
                    make_detection()
                ],
                make_performance(),
            )

            self.apply_sampling(
                monitor,
                state,
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "VERIFY",
            )

            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                2.0,
            )

            # t=6 : 2회
            runtime._handle_yolo_result(
                make_frame(6),
                [
                    make_detection()
                ],
                make_performance(),
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "VERIFY",
            )

            # t=16
            #
            # 15초 초과.
            #
            # Detection이 있어도
            # 같은 Frame에서 새 VERIFY를
            # 즉시 시작하면 안 된다.
            runtime._handle_yolo_result(
                make_frame(16),
                [
                    make_detection()
                ],
                make_performance(),
            )

            self.assertEqual(
                len(
                    saved_payloads
                ),
                0,
            )

            self.assertEqual(
                state[
                    "mode"
                ],
                "BASE",
            )

            self.apply_sampling(
                monitor,
                state,
            )

            self.assertEqual(
                sampler.get_interval(
                    1
                ),
                5.0,
            )

        print()
        print(
            "[PASS] "
            "VERIFY 15초 timeout "
            "→ Incident 없음 "
            "→ BASE 5s 복귀"
        )

    # ========================================================
    # TEST 4
    #
    # 실제 Runtime Poll 기본값
    # ========================================================

    def test_sampling_monitor_poll_interval(
        self,
    ) -> None:

        self.assertEqual(
            DEFAULT_SAMPLING_CHECK_INTERVAL_SEC,
            1.0,
        )

        print()
        print(
            "[PASS] "
            "SamplingPolicyMonitor "
            "Runtime poll 기본값 = 1초"
        )

    # ========================================================
    # TEST 5
    #
    # Runtime 정상 종료 중 VERIFY
    # → 원래 감시 모드 복귀
    # ========================================================

    def test_stop_restores_verify_mode(
        self,
    ) -> None:

        context = (
            self.make_runtime(
                initial_mode="ALERT"
            )
        )

        runtime = (
            context[
                "runtime"
            ]
        )

        state = (
            context[
                "state"
            ]
        )

        # Runtime이 ALERT → VERIFY 전환했던 상황을 재현.
        state[
            "mode"
        ] = "VERIFY"

        runtime._verify_restore_mode_by_cctv[
            1
        ] = "ALERT"

        with (
            patch(
                "ai.detection.incident_runtime.get_connection",
                new=fake_get_connection,
            ),
            patch.object(
                cctv_repository,
                "restore_from_verify_mode",
                side_effect=(
                    context[
                        "restore_from_verify_mode"
                    ]
                ),
            ),
            patch.object(
                CctvDetectionRuntime,
                "stop",
                return_value=None,
            ) as base_stop,
        ):

            runtime.stop()

        base_stop.assert_called_once_with()

        self.assertEqual(
            state[
                "mode"
            ],
            "ALERT",
        )

        self.assertEqual(
            runtime
            ._verify_restore_mode_by_cctv,
            {},
        )

        print()
        print(
            "[PASS] "
            "Runtime 정상 종료 "
            "→ VERIFY "
            "→ ALERT 복귀"
        )


if __name__ == "__main__":

    unittest.main(
        verbosity=2
    )