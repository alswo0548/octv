"""YOLO 분석 전 CCTV Frame의 영상 품질을 검사한다."""

import cv2
import numpy as np

from ..contracts import Frame

# 영상이 너무 어둡거나 너무 밝지 않은지 보는 함수
def _calculate_brightness_score(
    gray_image: np.ndarray,
) -> tuple[float, float]:
    """
    밝기 점수를 0~1 범위로 계산한다.

    반환값:
    - brightness_score
    - mean_brightness

    기준:
    - 평균 밝기 30~225: 정상 범위 → 1.0
    - 너무 어두우면 0에 가까워짐
    - 너무 밝으면 0에 가까워짐

    실제 UTIC CCTV를 확보한 뒤 기준값은 재조정한다.
    """

    # 흑백 이미지의 모든 픽셀 밝기 평균구하기.
    mean_brightness = float(
        np.mean(gray_image)
    )

    # 평균 밝기가 30보다 낮으면 점수를 깎음
    if mean_brightness < 30:
        score = mean_brightness / 30.0

    # 너무 밝아도 점수 깎음.
    elif mean_brightness > 225:
        score = (
            255.0 - mean_brightness
        ) / 30.0

    # 중간 범위면 정상 밝기로 보기
    else:
        score = 1.0

    score = max(
        0.0,
        min(1.0, score),
    )

    return (
        score,
        mean_brightness,
    )


# 영상이 흐린지 아닌지 보는 함수
def _calculate_sharpness_score(
    gray_image: np.ndarray,
) -> tuple[float, float]:
    """
    Laplacian variance를 이용해 흐림 정도를 계산한다.

    반환값:
    - sharpness_score
    - laplacian_variance

    variance가 높을수록 경계가 뚜렷한 영상이다.

    현재는 variance 100 이상을 충분히 선명한 영상으로 본다.
    실제 CCTV 영상 확보 후 재조정한다.
    """

    # Laplacian 이미지에서 경계 변화가 얼마나 많은지 보는 연산. 선명한 영상 -> 경계가 뚜렷해서 값 변화가 큼. 흐린영상 -> 경계가 뭉개져 있어서 변화가 적음.
    laplacian = cv2.Laplacian(
        gray_image,
        cv2.CV_64F,
    )

    # Laplacian 결과의 분산을 계산. variance 높으면 선명. 낮으면 흐림.
    variance = float(
        laplacian.var()
    )

    score = variance / 100.0

    score = max(
        0.0,
        min(1.0, score),
    )

    return (
        score,
        variance,
    )


# 실제로 호출할 메인 함수
def check_quality(
    frame: Frame,
    threshold: float = 0.60,
) -> dict:
    """
    CCTV Frame의 영상 품질을 검사한다.

    품질 점수:
    0.0 ~ 1.0

    현재 기준:
    - Frame 유효성
    - 밝기
    - 선명도

    quality_score가 threshold 이상이면
    YOLO 분석 가능 Frame으로 판단한다.
    """

    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            "threshold는 0.0~1.0 범위여야 합니다."
        )

    image = frame.image

    # -----------------------------------------------------
    # 1. Frame 유효성 검사
    # -----------------------------------------------------

    if (        # 이미지가 없거나, numpy 배열이 아니거나 빈 배열이면 분석 불가로 처리 -> YOLO로 보내지 않음.
        image is None
        or not isinstance(image, np.ndarray)
        or image.size == 0
    ):
        return {
            "is_acceptable": False,
            "quality_score": 0.0,
            "brightness_score": 0.0,
            "sharpness_score": 0.0,
            "mean_brightness": 0.0,
            "laplacian_variance": 0.0,
            "reason": "invalid_frame",
        }

    # OpenCV BGR 컬러 이미지 -> (H, W, 3) -> 이 구조가 아니면 분석 불가 처리 -> YOLO로 보내지 않음.
    if (
        image.ndim != 3
        or image.shape[2] != 3
    ):
        return {
            "is_acceptable": False,
            "quality_score": 0.0,
            "brightness_score": 0.0,
            "sharpness_score": 0.0,
            "mean_brightness": 0.0,
            "laplacian_variance": 0.0,
            "reason": "invalid_image_shape",
        }

    # -----------------------------------------------------
    # 2. Grayscale 변환
    # -----------------------------------------------------

    gray_image = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )

    # -----------------------------------------------------
    # 3. 밝기 검사
    # -----------------------------------------------------

    (
        brightness_score,
        mean_brightness,
    ) = _calculate_brightness_score(
        gray_image
    )

    # -----------------------------------------------------
    # 4. 선명도 검사
    # -----------------------------------------------------

    (
        sharpness_score,
        laplacian_variance,
    ) = _calculate_sharpness_score(
        gray_image
    )

    # -----------------------------------------------------
    # 5. 최종 품질 점수
    #
    # 한 항목이 심하게 나쁘면 분석을 보류할 수 있도록
    # 두 점수 중 낮은 값을 최종 점수로 사용한다.
    # -----------------------------------------------------

    quality_score = min(
        brightness_score,
        sharpness_score,
    )

    is_acceptable = (
        quality_score >= threshold
    )

    # -----------------------------------------------------
    # 6. 실패 원인
    # -----------------------------------------------------

    if is_acceptable:
        reason = "ok"

    elif mean_brightness < 30:
        reason = "too_dark"

    elif mean_brightness > 225:
        reason = "too_bright"

    elif sharpness_score < threshold:
        reason = "too_blurry"

    else:
        reason = "quality_below_threshold"

    return {
        "is_acceptable": is_acceptable,
        "quality_score": quality_score,
        "brightness_score": brightness_score,
        "sharpness_score": sharpness_score,
        "mean_brightness": mean_brightness,
        "laplacian_variance": laplacian_variance,
        "reason": reason,
    }