from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np

from ai.contracts import Frame
from ai.detection.quality import check_quality


ROOT = Path(__file__).resolve().parents[1]

VIDEO_PATH = (
    ROOT
    / "local_data"
    / "cctv_test"
    / "sample.mp4"
)

QUALITY_THRESHOLD = 0.60

KST = ZoneInfo("Asia/Seoul")


def load_frame() -> np.ndarray:
    cap = cv2.VideoCapture(
        str(VIDEO_PATH)
    )

    try:
        if not cap.isOpened():
            raise RuntimeError(
                f"영상을 열 수 없습니다: {VIDEO_PATH}"
            )

        success, image = cap.read()

        if not success or image is None:
            raise RuntimeError(
                "테스트 Frame을 읽을 수 없습니다."
            )

        return image

    finally:
        cap.release()


def make_frame(
    image: np.ndarray,
) -> Frame:
    return Frame(
        cctv_id=1,
        captured_at=datetime.now(KST),
        image=image,
    )


def print_result(
    name: str,
    image: np.ndarray,
) -> None:
    frame = make_frame(
        image
    )

    result = check_quality(
        frame,
        threshold=QUALITY_THRESHOLD,
    )

    print()
    print(
        f"[{name}]"
    )

    print(
        f"Quality Score      : "
        f"{result['quality_score']:.4f}"
    )

    print(
        f"Brightness Score   : "
        f"{result['brightness_score']:.4f}"
    )

    print(
        f"Sharpness Score    : "
        f"{result['sharpness_score']:.4f}"
    )

    print(
        f"Mean Brightness    : "
        f"{result['mean_brightness']:.2f}"
    )

    print(
        f"Laplacian Variance : "
        f"{result['laplacian_variance']:.2f}"
    )

    print(
        f"Result             : "
        f"{'PASS' if result['is_acceptable'] else 'FAIL'}"
    )

    print(
        f"Reason             : "
        f"{result['reason']}"
    )


def main() -> None:
    original = load_frame()

    # =====================================================
    # 1. 정상 영상
    # =====================================================

    normal_image = (
        original.copy()
    )

    # =====================================================
    # 2. 매우 어두운 영상
    # =====================================================

    dark_image = (
        original.astype(
            np.float32
        )
        * 0.05
    ).astype(
        np.uint8
    )

    # =====================================================
    # 3. 과노출 영상
    # =====================================================

    bright_image = np.full_like(
        original,
        250,
    )

    # =====================================================
    # 4. 심하게 흐린 영상
    # =====================================================

    blurry_image = cv2.GaussianBlur(
        original,
        (101, 101),
        0,
    )

    print("=" * 70)
    print("OCTV QUALITY FAILURE TEST")
    print("=" * 70)
    print(
        f"Threshold: {QUALITY_THRESHOLD:.2f}"
    )

    print_result(
        "NORMAL",
        normal_image,
    )

    print_result(
        "DARK",
        dark_image,
    )

    print_result(
        "OVEREXPOSED",
        bright_image,
    )

    print_result(
        "BLURRY",
        blurry_image,
    )


if __name__ == "__main__":
    main()