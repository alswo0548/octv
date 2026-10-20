"""CCTV Runtime에 Incident Pipeline과 VERIFY 제어를 연결합니다."""

from __future__ import annotations

from ai.contracts import (
    Detection,
    Frame,
)

from ai.detection.cctv_runtime import (
    CctvDetectionRuntime,
)

from ai.detection.incident_pipeline import (
    IncidentPipeline,
    IncidentPipelineConfig,
)

from ai.detection.yolo_worker import (
    YoloPerformance,
)

from backend.app.cctvs import (
    repository as cctv_repository,
)

from backend.app.db.session import (
    get_connection,
)


class IncidentAwareCctvDetectionRuntime(
    CctvDetectionRuntime
):
    """
    실제 운영 CCTV Runtime.

    전체 흐름:

    CCTV Frame
        ↓
    Sampling
        ↓
    Quality Check
        ↓
    YOLO
        ↓
    위험 후보
        ↓
    CCTV monitored_mode = VERIFY
        ↓
    VERIFY 분석 주기 적용
        ↓
    최대 validation window 동안 반복 확인
        ↓
    최소 탐지 횟수 충족
        ↓
    Incident 생성 / 갱신
        ↓
    원래 BASE / ALERT / POST_ALERT 복귀

    DB 구조는 변경하지 않는다.

    기존:
        monitoring_settings
        cctvs.monitored_mode

    만 사용한다.
    """

    def __init__(
        self,
        *args,
        incident_pipeline: (
            IncidentPipeline
            | None
        ) = None,
        **kwargs,
    ) -> None:

        super().__init__(
            *args,
            **kwargs,
        )

        # CCTV가 VERIFY에 들어가기 전
        # 원래 어떤 감시 모드였는지
        # Runtime 메모리에만 보관한다.
        #
        # DB 컬럼은 추가하지 않는다.
        self._verify_restore_mode_by_cctv: dict[
            int,
            str,
        ] = {}

        # 테스트에서 Pipeline을 직접 주입한 경우.
        if incident_pipeline is not None:

            self._incident_pipeline = (
                incident_pipeline
            )

            return

        settings = (
            self._load_monitoring_settings()
        )

        incident_config = (
            IncidentPipelineConfig
            .from_settings(
                settings
            )
        )

        self._incident_pipeline = (
            IncidentPipeline(
                config=(
                    incident_config
                )
            )
        )

        print(
            "[INCIDENT RUNTIME] "
            "monitoring_settings 적용 "
            f"/ candidate_confidence="
            f"{incident_config.candidate_confidence_threshold:.2f} "
            f"/ incident_confidence="
            f"{incident_config.incident_confidence_threshold:.2f} "
            f"/ min_hits="
            f"{incident_config.candidate_min_detection_count} "
            f"/ validation_window="
            f"{incident_config.temporal_validation_sec:.1f}s"
        )

    # =====================================================
    # YOLO Result
    # =====================================================

    def _handle_yolo_result(
        self,
        frame: Frame,
        detections: list[
            Detection
        ],
        performance: YoloPerformance,
    ) -> None:
        """
        YOLO 결과를 Incident Pipeline으로 전달하고
        Temporal 상태에 맞게 VERIFY 모드를 제어한다.

        Detection이 없는 Frame도
        Pipeline에 반드시 전달한다.
        """

        # 기존 Detection 로그 유지.
        super()._handle_yolo_result(
            frame,
            detections,
            performance,
        )

        result = (
            self._incident_pipeline
            .handle_result(
                frame=frame,
                detections=detections,
                performance=performance,
            )
        )

        # 기존 테스트 Fake Pipeline 등과의
        # 호환성을 위해 None이면
        # VERIFY 제어를 수행하지 않는다.
        if result is None:
            return

        # Pipeline 자체 오류가 발생한 경우에는
        # 현재 VERIFY 상태를 임의로 바꾸지 않는다.
        if result.had_error:
            return

        cctv_id = int(
            frame.cctv_id
        )

        # 아직 검증 중인 hazard가 하나라도 있으면
        # VERIFY를 유지한다.
        if result.pending_hazards:

            self._ensure_verify_mode(
                cctv_id=cctv_id,
                pending_hazards=(
                    result.pending_hazards
                ),
            )

            return

        # pending hazard가 없어졌다면
        # VERIFY 세션이 성공 또는 실패로 끝난 것.
        self._restore_verify_mode(
            cctv_id=cctv_id
        )

    # =====================================================
    # VERIFY 진입
    # =====================================================

    def _ensure_verify_mode(
        self,
        cctv_id: int,
        pending_hazards: tuple[
            str,
            ...
        ],
    ) -> None:

        # 이미 이 Runtime이 VERIFY 전환을 수행했고
        # 원래 모드를 기억하고 있으면
        # 중복 DB UPDATE를 하지 않는다.
        if (
            cctv_id
            in self
            ._verify_restore_mode_by_cctv
        ):
            return

        try:

            with get_connection() as connection:

                transition = (
                    cctv_repository
                    .enter_verify_mode(
                        connection,
                        cctv_id,
                    )
                )

        except Exception as exc:

            print(
                "[VERIFY MODE ERROR] "
                "VERIFY 전환 실패 "
                f"/ cctv={cctv_id} "
                f"/ error={exc}"
            )

            return

        if (
            transition[
                "changed"
            ]
        ):

            previous_mode = (
                transition[
                    "previous_mode"
                ]
            )

            if previous_mode is None:

                return

            self._verify_restore_mode_by_cctv[
                cctv_id
            ] = str(
                previous_mode
            )

            print(
                "[VERIFY MODE] "
                f"CCTV {cctv_id} "
                f"/ {previous_mode} "
                "→ VERIFY "
                f"/ pending="
                f"{','.join(pending_hazards)}"
            )

            return

        current_mode = str(
            transition[
                "monitored_mode"
            ]
        )

        # 다른 실행 흐름에 의해 이미 VERIFY라면
        # 이전 모드를 알 수 없으므로
        # 임의의 복귀 모드를 만들지 않는다.
        if current_mode == "VERIFY":

            print(
                "[VERIFY MODE] "
                f"CCTV {cctv_id} "
                "/ 이미 VERIFY "
                "/ restore mode 미확인"
            )

    # =====================================================
    # VERIFY 복귀
    # =====================================================

    def _restore_verify_mode(
        self,
        cctv_id: int,
    ) -> None:

        restore_mode = (
            self
            ._verify_restore_mode_by_cctv
            .get(
                cctv_id
            )
        )

        if restore_mode is None:
            return

        try:

            with get_connection() as connection:

                row = (
                    cctv_repository
                    .restore_from_verify_mode(
                        connection,
                        cctv_id=cctv_id,
                        restore_mode=(
                            restore_mode
                        ),
                    )
                )

        except Exception as exc:

            print(
                "[VERIFY MODE ERROR] "
                "VERIFY 복귀 실패 "
                f"/ cctv={cctv_id} "
                f"/ restore="
                f"{restore_mode} "
                f"/ error={exc}"
            )

            # DB 복귀에 실패하면
            # 다음 Frame에서 다시 시도할 수 있도록
            # 메모리 상태를 유지한다.
            return

        # DB가 이미 다른 상태로 변경되어 있더라도
        # VERIFY가 아니므로 이 Runtime의 세션은 종료한다.
        self._verify_restore_mode_by_cctv.pop(
            cctv_id,
            None,
        )

        if row is None:

            print(
                "[VERIFY MODE] "
                f"CCTV {cctv_id} "
                "/ VERIFY 복귀 UPDATE 생략 "
                "/ DB 상태가 이미 변경됨"
            )

            return

        print(
            "[VERIFY MODE] "
            f"CCTV {cctv_id} "
            f"/ VERIFY "
            f"→ {restore_mode}"
        )