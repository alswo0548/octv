"""YOLO 모델 로딩·추론을 담당한다."""

from pathlib import Path

import numpy as np
from ultralytics import YOLO

from ..contracts import Detection, Frame


class YoloDetector:
    """
    YOLO 모델을 한 번 로드한 뒤 반복해서 추론한다.

    현재 yolo11s.pt는 전체 파이프라인 검증용 임시 모델이다.
    이후 OCTV 학습이 완료되면 best.pt 경로로 교체한다.
    """

    def __init__(
        self,
        model_path: str | Path,
        imgsz: int = 640,
        device: str = "cpu",
        confidence: float = 0.25,
    ):
        self.model_path = Path(model_path)
        self.imgsz = imgsz
        self.device = device
        self.confidence = confidence

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"YOLO 모델을 찾을 수 없습니다: "
                f"{self.model_path}"
            )

        print(
            f"[YOLO DETECTOR] 모델 로딩 시작 "
            f"/ path={self.model_path}"
        )

        self.model = YOLO(
            str(self.model_path)
        )

        self.model_version = (
            self.model_path.name
        )

        print(
            f"[YOLO DETECTOR] 모델 로딩 완료 "
            f"/ model={self.model_version} "
            f"/ device={self.device}"
        )

    def warmup(self) -> None:
        """
        실제 분석 전에 한 번 추론해 내부 초기화를 수행한다.

        첫 실제 CCTV Frame에서 초기화 지연이 발생하는 것을 줄인다.
        """

        dummy_image = np.zeros(
            (
                self.imgsz,
                self.imgsz,
                3,
            ),
            dtype=np.uint8,
        )

        print("[YOLO DETECTOR] Warm-up 시작")

        self.model.predict(
            source=dummy_image,
            imgsz=self.imgsz,
            device=self.device,
            conf=self.confidence,
            verbose=False,
        )

        print("[YOLO DETECTOR] Warm-up 완료")

    def detect(
        self,
        frame: Frame,
    ) -> list[Detection]:
        """
        Frame.image를 YOLO로 추론하고
        Detection 목록으로 변환한다.
        """

        results = self.model.predict(
            source=frame.image,
            imgsz=self.imgsz,
            device=self.device,
            conf=self.confidence,
            verbose=False,
        )

        result = results[0]

        detections: list[Detection] = []

        if result.boxes is None:
            return detections

        boxes = result.boxes.xyxy.cpu().tolist()
        confidences = (
            result.boxes.conf.cpu().tolist()
        )
        class_ids = (
            result.boxes.cls.cpu().tolist()
        )

        for bbox, confidence, class_id in zip(
            boxes,
            confidences,
            class_ids,
        ):
            class_index = int(class_id)

            class_name = result.names[
                class_index
            ]

            x1, y1, x2, y2 = bbox

            detections.append(
                Detection(
                    hazard_type=class_name,
                    confidence=float(confidence),
                    bbox=(
                        float(x1),
                        float(y1),
                        float(x2),
                        float(y2),
                    ),
                    model_version=self.model_version,
                )
            )

        return detections