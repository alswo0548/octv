"""CCTV Runtime에 Incident Pipeline을 연결합니다."""

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
)
from ai.detection.yolo_worker import (
    YoloPerformance,
)


class IncidentAwareCctvDetectionRuntime(
    CctvDetectionRuntime
):
    """
    기존 검증 완료 CCTV Runtime에

    YOLO
        ↓
    후보 필터
        ↓
    시간 검증
        ↓
    Incident 저장

    을 추가한 실제 운영 Runtime.
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

        self._incident_pipeline = (
            incident_pipeline
            if incident_pipeline
            is not None
            else IncidentPipeline()
        )

    def _handle_yolo_result(
        self,
        frame: Frame,
        detections: list[
            Detection
        ],
        performance: YoloPerformance,
    ) -> None:

        # 기존 Runtime 로그는 그대로 유지한다.
        super()._handle_yolo_result(
            frame,
            detections,
            performance,
        )

        # Incident Pipeline 연결
        self._incident_pipeline.handle_result(
            frame=frame,
            detections=detections,
            performance=performance,
        )