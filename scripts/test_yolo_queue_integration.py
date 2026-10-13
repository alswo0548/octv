"""AnalysisFrameQueue → YoloWorker → 실제 YOLO 추론 통합 테스트."""

from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

import numpy as np

from ai.contracts import Frame
from ai.detection.detector import YoloDetector
from ai.detection.frame_queue import AnalysisFrameQueue
from ai.detection.yolo_worker import (
    YoloPerformance,
    YoloWorker,
)


ROOT = Path(__file__).resolve().parents[1]

MODEL_PATH = (
    ROOT
    / "yolo11s.pt"
)

KST = ZoneInfo(
    "Asia/Seoul"
)

CCTV_ID = 1


def main() -> None:

    print("=" * 70)
    print("YOLO QUEUE INTEGRATION TEST")
    print("=" * 70)

    # =====================================================
    # 1. 모델 확인
    # =====================================================

    print()

    print(
        "[1] YOLO 모델 확인"
    )

    print(
        f"Model Path : "
        f"{MODEL_PATH}"
    )

    if not MODEL_PATH.exists():

        raise FileNotFoundError(
            f"YOLO 모델을 찾을 수 없습니다: "
            f"{MODEL_PATH}"
        )

    print(
        "[PASS] 모델 파일 확인"
    )

    # =====================================================
    # 2. Detector 생성
    # =====================================================

    print()

    print(
        "[2] YoloDetector 생성"
    )

    detector = YoloDetector(
        model_path=MODEL_PATH,
        imgsz=640,
        device="cpu",
        confidence=0.25,
    )

    detector.warmup()

    print(
        "[PASS] Detector 준비 완료"
    )

    # =====================================================
    # 3. Queue 생성
    # =====================================================

    print()

    print(
        "[3] AnalysisFrameQueue 생성"
    )

    frame_queue = (
        AnalysisFrameQueue(
            maxsize=4,
        )
    )

    print(
        f"Queue maxsize : 4"
    )

    print(
        "[PASS] Queue 생성 완료"
    )

    # =====================================================
    # 4. 테스트 상태
    # =====================================================

    result_event = Event()

    status_lock = Lock()

    status_history: list[str] = []

    result_holder: dict = {}

    # =====================================================
    # 5. YOLO Callback
    # =====================================================

    def handle_result(
        frame: Frame,
        detections,
        performance: YoloPerformance,
    ) -> None:

        print()

        print(
            "[YOLO RESULT]"
        )

        print(
            f"CCTV ID       : "
            f"{frame.cctv_id}"
        )

        print(
            f"Captured At   : "
            f"{frame.captured_at}"
        )

        print(
            f"Detection 수  : "
            f"{len(detections)}"
        )

        print(
            f"Queue Wait    : "
            f"{performance.queue_wait_sec:.4f}초"
        )

        print(
            f"Inference     : "
            f"{performance.inference_sec:.4f}초"
        )

        print(
            f"Total Latency : "
            f"{performance.total_latency_sec:.4f}초"
        )

        if detections:

            print()

            print(
                "[DETECTIONS]"
            )

            for index, detection in enumerate(
                detections,
                start=1,
            ):

                print(
                    f"#{index} "
                    f"type="
                    f"{detection.hazard_type} "
                    f"/ confidence="
                    f"{detection.confidence:.3f} "
                    f"/ bbox="
                    f"{detection.bbox} "
                    f"/ model="
                    f"{detection.model_version}"
                )

        else:

            print(
                "Detection 없음 "
                "(검은 테스트 이미지이므로 정상)"
            )

        result_holder[
            "frame"
        ] = frame

        result_holder[
            "detections"
        ] = detections

        result_holder[
            "performance"
        ] = performance

        result_event.set()

    # =====================================================
    # 6. 상태 Callback
    # =====================================================

    def handle_status(
        cctv_id: int,
        status: str,
    ) -> None:

        print(
            f"[YOLO STATUS] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

        with status_lock:

            status_history.append(
                status
            )

    # =====================================================
    # 7. Worker 생성
    # =====================================================

    print()

    print(
        "[4] YoloWorker 생성"
    )

    worker = YoloWorker(
        frame_queue=frame_queue,
        detect_fn=detector.detect,
        poll_interval_sec=0.1,
    )

    worker_thread = Thread(
        target=worker.run,
        kwargs={
            "on_result":
                handle_result,

            "on_status":
                handle_status,
        },
        name="yolo-queue-integration-test",
    )

    worker_thread.start()

    print(
        "[PASS] YoloWorker 시작"
    )

    # =====================================================
    # 8. 테스트 Frame 생성
    # =====================================================

    print()

    print(
        "[5] 테스트 Frame 생성"
    )

    image = np.zeros(
        (
            480,
            720,
            3,
        ),
        dtype=np.uint8,
    )

    frame = Frame(
        cctv_id=CCTV_ID,
        captured_at=datetime.now(
            KST
        ),
        image=image,
    )

    print(
        f"Frame shape : "
        f"{frame.image.shape}"
    )

    # =====================================================
    # 9. Queue 삽입
    # =====================================================

    print()

    print(
        "[6] Frame → Queue"
    )

    dropped_frame = (
        frame_queue.put_latest(
            frame
        )
    )

    print(
        f"Queue size    : "
        f"{frame_queue.size()}"
    )

    print(
        f"Dropped Frame : "
        f"{dropped_frame}"
    )

    if dropped_frame is not None:

        raise AssertionError(
            "Queue 첫 삽입에서 "
            "Frame이 제거되었습니다."
        )

    print(
        "[PASS] Frame Queue 삽입"
    )

    # =====================================================
    # 10. 실제 YOLO 결과 대기
    # =====================================================

    print()

    print(
        "[7] YOLO 실제 추론 결과 대기"
    )

    if not result_event.wait(
        timeout=30
    ):

        worker.stop()

        worker_thread.join(
            timeout=5
        )

        raise AssertionError(
            "30초 안에 YOLO 결과를 "
            "받지 못했습니다."
        )

    print(
        "[PASS] 실제 YOLO 결과 수신"
    )

    # =====================================================
    # 11. 결과 기본 검증
    # =====================================================

    processed_frame = (
        result_holder[
            "frame"
        ]
    )

    performance = (
        result_holder[
            "performance"
        ]
    )

    if (
        processed_frame.cctv_id
        != CCTV_ID
    ):

        raise AssertionError(
            "처리된 CCTV ID가 "
            "일치하지 않습니다."
        )

    if (
        performance.inference_sec
        <= 0
    ):

        raise AssertionError(
            "YOLO inference 시간이 "
            "0 이하입니다."
        )

    with status_lock:

        running_seen = (
            "RUNNING"
            in status_history
        )

    if not running_seen:

        raise AssertionError(
            "YOLO 성공 후 "
            "RUNNING 상태가 "
            "발생하지 않았습니다."
        )

    print(
        "[PASS] RUNNING 상태 확인"
    )

    # =====================================================
    # 12. Worker 종료
    # =====================================================

    print()

    print(
        "[8] YoloWorker 종료"
    )

    worker.stop()

    worker_thread.join(
        timeout=5
    )

    if worker_thread.is_alive():

        raise AssertionError(
            "YoloWorker Thread가 "
            "종료되지 않았습니다."
        )

    with status_lock:

        final_status_history = (
            status_history.copy()
        )

    if (
        not final_status_history
        or final_status_history[-1]
        != "STOPPED"
    ):

        raise AssertionError(
            "YoloWorker 종료 후 "
            "STOPPED 상태가 "
            "발생하지 않았습니다."
        )

    print(
        "[PASS] STOPPED 상태 확인"
    )

    # =====================================================
    # 결과
    # =====================================================

    detections = (
        result_holder[
            "detections"
        ]
    )

    print()

    print("=" * 70)

    print(
        "RESULT"
    )

    print("=" * 70)

    print(
        f"Model             : "
        f"{MODEL_PATH.name}"
    )

    print(
        f"CCTV ID           : "
        f"{CCTV_ID}"
    )

    print(
        f"Detection Count   : "
        f"{len(detections)}"
    )

    print(
        f"Queue Wait        : "
        f"{performance.queue_wait_sec:.4f}초"
    )

    print(
        f"Inference         : "
        f"{performance.inference_sec:.4f}초"
    )

    print(
        f"Total Latency     : "
        f"{performance.total_latency_sec:.4f}초"
    )

    print(
        "Status History    : "
        + " → ".join(
            final_status_history
        )
    )

    print()

    print(
        "[SUCCESS] "
        "AnalysisFrameQueue "
        "→ YoloWorker "
        "→ YoloDetector "
        "실제 추론 통합 정상"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()