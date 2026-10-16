"""YOLO Detection을 시간 검증한 뒤 Incident로 저장하는 Pipeline."""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

import cv2

from ai.contracts import (
    Detection,
    Frame,
    IncidentCandidate,
)
from ai.detection.yolo_worker import (
    YoloPerformance,
)
from backend.app.incidents.service import (
    register_detection,
)


# =========================================================
# OCTV가 실제 사건 후보로 취급하는 재난 Class
# =========================================================

ALLOWED_HAZARD_TYPES = frozenset(
    {
        "flood",
        "fallen_tree",
        "severe_road_damage",
        "road_obstacle",
    }
)


# =========================================================
# 설정
# =========================================================


@dataclass(frozen=True)
class IncidentPipelineConfig:
    """
    YOLO 결과 → 사건 후보 → 시간 검증 설정.

    min_confidence:
        YOLO 결과 중 사건 후보로 볼 최소 confidence.

    min_area_ratio:
        전체 Frame 대비 bbox 최소 면적 비율.

    temporal_window_size:
        시간 검증에 사용할 최근 분석 Frame 수.

    temporal_min_hits:
        최근 분석 Frame window 안에서
        같은 재난이 탐지되어야 하는 최소 횟수.

    기본 정책:
        최근 5개 분석 Frame 중
        같은 재난이 3개 이상에서 탐지되면
        시간 검증 성공.

    track_ttl_sec:
        오랫동안 Frame 상태가 갱신되지 않은
        임시 후보 Track 제거 시간.

    jpeg_quality:
        사건 대표 이미지 JPEG 품질.
    """

    min_confidence: float = 0.35
    min_area_ratio: float = 0.0005

    temporal_window_size: int = 5
    temporal_min_hits: int = 3

    track_ttl_sec: float = 60.0

    jpeg_quality: int = 90

    def __post_init__(self) -> None:

        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError(
                "min_confidence는 0~1이어야 합니다."
            )

        if not 0.0 <= self.min_area_ratio <= 1.0:
            raise ValueError(
                "min_area_ratio는 0~1이어야 합니다."
            )

        if self.temporal_window_size <= 0:
            raise ValueError(
                "temporal_window_size는 "
                "1 이상이어야 합니다."
            )

        if self.temporal_min_hits <= 0:
            raise ValueError(
                "temporal_min_hits는 "
                "1 이상이어야 합니다."
            )

        if (
            self.temporal_min_hits
            > self.temporal_window_size
        ):
            raise ValueError(
                "temporal_min_hits는 "
                "temporal_window_size보다 "
                "클 수 없습니다."
            )

        if self.track_ttl_sec <= 0:
            raise ValueError(
                "track_ttl_sec은 "
                "0보다 커야 합니다."
            )

        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError(
                "jpeg_quality는 "
                "1~100이어야 합니다."
            )

    @classmethod
    def from_env(
        cls,
    ) -> "IncidentPipelineConfig":

        return cls(
            min_confidence=float(
                os.getenv(
                    "OCTV_CANDIDATE_MIN_CONFIDENCE",
                    "0.35",
                )
            ),
            min_area_ratio=float(
                os.getenv(
                    "OCTV_CANDIDATE_MIN_AREA_RATIO",
                    "0.0005",
                )
            ),
            temporal_window_size=int(
                os.getenv(
                    "OCTV_TEMPORAL_WINDOW_SIZE",
                    "5",
                )
            ),
            temporal_min_hits=int(
                os.getenv(
                    "OCTV_TEMPORAL_MIN_HITS",
                    "3",
                )
            ),
            track_ttl_sec=float(
                os.getenv(
                    "OCTV_TEMPORAL_TRACK_TTL_SEC",
                    "60",
                )
            ),
            jpeg_quality=int(
                os.getenv(
                    "OCTV_INCIDENT_JPEG_QUALITY",
                    "90",
                )
            ),
        )


# =========================================================
# 후보 Filter
# =========================================================


class DetectionCandidateFilter:
    """
    YOLO 결과 중 실제 OCTV 재난 후보만 남긴다.

    같은 Frame에서 같은 hazard_type이
    여러 개 탐지된 경우에는
    confidence가 가장 높은 Detection 하나를 사용한다.
    """

    def __init__(
        self,
        config: IncidentPipelineConfig,
    ) -> None:

        self._config = config

    def select(
        self,
        frame: Frame,
        detections: list[Detection],
    ) -> dict[str, Detection]:

        selected: dict[
            str,
            Detection,
        ] = {}

        for detection in detections:

            hazard_type = (
                detection.hazard_type
            )

            if (
                hazard_type
                not in ALLOWED_HAZARD_TYPES
            ):
                continue

            if (
                detection.confidence
                < self._config.min_confidence
            ):
                continue

            area_ratio = (
                self._bbox_area_ratio(
                    frame=frame,
                    detection=detection,
                )
            )

            if (
                area_ratio
                < self._config.min_area_ratio
            ):
                continue

            previous = (
                selected.get(
                    hazard_type
                )
            )

            if (
                previous is None
                or detection.confidence
                > previous.confidence
            ):
                selected[
                    hazard_type
                ] = detection

        return selected

    @staticmethod
    def _bbox_area_ratio(
        frame: Frame,
        detection: Detection,
    ) -> float:

        if frame.image is None:
            return 0.0

        if frame.image.ndim < 2:
            return 0.0

        height = int(
            frame.image.shape[0]
        )

        width = int(
            frame.image.shape[1]
        )

        if (
            width <= 0
            or height <= 0
        ):
            return 0.0

        (
            x1,
            y1,
            x2,
            y2,
        ) = detection.bbox

        left = max(
            0.0,
            min(
                float(x1),
                float(width),
            ),
        )

        top = max(
            0.0,
            min(
                float(y1),
                float(height),
            ),
        )

        right = max(
            0.0,
            min(
                float(x2),
                float(width),
            ),
        )

        bottom = max(
            0.0,
            min(
                float(y2),
                float(height),
            ),
        )

        box_width = max(
            0.0,
            right - left,
        )

        box_height = max(
            0.0,
            bottom - top,
        )

        frame_area = float(
            width * height
        )

        if frame_area <= 0:
            return 0.0

        return (
            box_width
            * box_height
            / frame_area
        )


# =========================================================
# Temporal Verification 내부 상태
# =========================================================


@dataclass(frozen=True)
class _TemporalSample:
    captured_at: datetime
    detection: Detection | None


@dataclass
class _TemporalTrack:
    samples: deque[
        _TemporalSample
    ] = field(
        default_factory=deque
    )

    last_sample_at: datetime | None = None

    # 같은 후보 구간에서 처음 재난이 탐지된 시각.
    #
    # Sliding Window의 첫 positive가 아니라
    # 후보 구간 전체의 최초 positive를 유지한다.
    first_positive_at: datetime | None = None


# =========================================================
# Temporal Verifier
# =========================================================


class TemporalIncidentVerifier:
    """
    최근 N개 분석 Frame 중
    같은 hazard가 M번 이상 등장했는지 확인한다.

    OCTV 기본 정책:
        최근 5개 분석 Frame 중
        동일 hazard가 3회 이상 탐지.

    예:
        Frame 1: O
        Frame 2: X
        Frame 3: O
        Frame 4: X
        Frame 5: O

        → 최근 5 Frame 중 3회 탐지
        → 시간 검증 성공.

    duration_sec:
        Sliding Window 내부 첫 positive가 아니라
        현재 재난 후보 구간의 최초 positive부터 계산한다.

        따라서 같은 후보가 지속되는 동안
        duration_sec은 감소하지 않는다.

    후보 초기화:
        최근 Window 안에서 해당 hazard의
        positive가 완전히 사라지면
        이전 후보 구간이 끝난 것으로 보고
        first_positive_at을 초기화한다.
    """

    def __init__(
        self,
        config: IncidentPipelineConfig,
    ) -> None:

        self._config = config

        self._tracks: dict[
            tuple[int, str],
            _TemporalTrack,
        ] = {}

    def observe(
        self,
        frame: Frame,
        detections_by_hazard: Mapping[
            str,
            Detection,
        ],
    ) -> list[IncidentCandidate]:

        self._cleanup_stale_tracks(
            current_at=(
                frame.captured_at
            )
        )

        cctv_id = int(
            frame.cctv_id
        )

        existing_hazards = {
            hazard_type
            for (
                track_cctv_id,
                hazard_type,
            ) in self._tracks
            if track_cctv_id
            == cctv_id
        }

        observed_hazards = (
            existing_hazards
            | set(
                detections_by_hazard.keys()
            )
        )

        verified: list[
            IncidentCandidate
        ] = []

        for hazard_type in sorted(
            observed_hazards
        ):

            key = (
                cctv_id,
                hazard_type,
            )

            track = (
                self._tracks.get(
                    key
                )
            )

            if track is None:

                track = _TemporalTrack(
                    samples=deque(
                        maxlen=(
                            self
                            ._config
                            .temporal_window_size
                        )
                    )
                )

                self._tracks[
                    key
                ] = track

            # 이미 처리한 시각과 같거나
            # 더 오래된 Frame은
            # Temporal 상태에 다시 넣지 않는다.
            if (
                track.last_sample_at
                is not None
                and frame.captured_at
                <= track.last_sample_at
            ):
                continue

            detection = (
                detections_by_hazard.get(
                    hazard_type
                )
            )

            # -------------------------------------------------
            # 현재 후보 구간 최초 positive 기록
            # -------------------------------------------------

            if (
                detection is not None
                and track.first_positive_at
                is None
            ):
                track.first_positive_at = (
                    frame.captured_at
                )

            # -------------------------------------------------
            # 현재 Frame을 Sliding Window에 추가
            # -------------------------------------------------

            track.samples.append(
                _TemporalSample(
                    captured_at=(
                        frame.captured_at
                    ),
                    detection=(
                        detection
                    ),
                )
            )

            track.last_sample_at = (
                frame.captured_at
            )

            positive_samples = [
                sample
                for sample
                in track.samples
                if sample.detection
                is not None
            ]

            hit_count = len(
                positive_samples
            )

            # -------------------------------------------------
            # 최근 Window에 positive가 하나도 없으면
            # 이전 후보 구간 종료
            # -------------------------------------------------

            if hit_count == 0:

                track.first_positive_at = (
                    None
                )

                continue

            # 현재 Frame 자체가 미탐이면
            # 사건 생성/갱신은 하지 않는다.
            #
            # 하지만 Window와 최초 positive 상태는
            # 계속 유지한다.
            if detection is None:
                continue

            print(
                "[TEMPORAL] "
                f"CCTV {cctv_id} "
                f"/ hazard={hazard_type} "
                f"/ hits={hit_count}"
                f"/{len(track.samples)} "
                f"/ required="
                f"{self._config.temporal_min_hits}"
                f"/{self._config.temporal_window_size}"
            )

            if (
                hit_count
                < self._config.temporal_min_hits
            ):
                continue

            if (
                track.first_positive_at
                is None
            ):
                raise RuntimeError(
                    "Temporal Track의 "
                    "first_positive_at이 없습니다."
                )

            duration_sec = max(
                0,
                int(
                    (
                        frame.captured_at
                        - track.first_positive_at
                    ).total_seconds()
                ),
            )

            verified.append(
                IncidentCandidate(
                    frame=frame,
                    detection=detection,
                    duration_sec=(
                        duration_sec
                    ),
                    dedup_key=(
                        self._build_dedup_key(
                            cctv_id=(
                                cctv_id
                            ),
                            hazard_type=(
                                hazard_type
                            ),
                        )
                    ),
                )
            )

        return verified

    @staticmethod
    def _build_dedup_key(
        cctv_id: int,
        hazard_type: str,
    ) -> str:

        return (
            f"cctv:{cctv_id}:"
            f"hazard:{hazard_type}"
        )

    def _cleanup_stale_tracks(
        self,
        current_at: datetime,
    ) -> None:

        stale_keys: list[
            tuple[int, str]
        ] = []

        for (
            key,
            track,
        ) in self._tracks.items():

            if (
                track.last_sample_at
                is None
            ):
                stale_keys.append(
                    key
                )

                continue

            age_sec = (
                current_at
                - track.last_sample_at
            ).total_seconds()

            if (
                age_sec
                > self._config.track_ttl_sec
            ):
                stale_keys.append(
                    key
                )

        for key in stale_keys:

            self._tracks.pop(
                key,
                None,
            )


# =========================================================
# Incident Pipeline
# =========================================================


class IncidentPipeline:
    """
    YOLO 결과를 사건 저장까지 연결한다.

    흐름:

    Detection
        ↓
    OCTV hazard class 확인
        ↓
    confidence / bbox area filter
        ↓
    Temporal Verification
        최근 5 Frame 중 3회 이상
        ↓
    IncidentCandidate
        ↓
    Frame JPEG encode
        ↓
    incidents.service.register_detection()
        ↓
    새 Incident INSERT
    또는 진행 사건 UPSERT

    Notification 중복 알림 제한은
    이 Pipeline에서 처리하지 않는다.

    Incident 생성/갱신과
    사용자 알림 cooldown은
    별도 단계로 관리한다.
    """

    def __init__(
        self,
        config: (
            IncidentPipelineConfig
            | None
        ) = None,
        register_fn: Callable[
            [dict],
            object,
        ] = register_detection,
    ) -> None:

        self._config = (
            config
            if config is not None
            else (
                IncidentPipelineConfig
                .from_env()
            )
        )

        self._candidate_filter = (
            DetectionCandidateFilter(
                config=(
                    self._config
                )
            )
        )

        self._temporal_verifier = (
            TemporalIncidentVerifier(
                config=(
                    self._config
                )
            )
        )

        self._register_fn = (
            register_fn
        )

        print(
            "[INCIDENT PIPELINE] "
            "초기화 "
            f"/ confidence>="
            f"{self._config.min_confidence:.2f} "
            f"/ area_ratio>="
            f"{self._config.min_area_ratio:.6f} "
            f"/ temporal="
            f"{self._config.temporal_min_hits}"
            f"/"
            f"{self._config.temporal_window_size}"
        )

    def handle_result(
        self,
        frame: Frame,
        detections: list[
            Detection
        ],
        performance: (
            YoloPerformance
            | None
        ) = None,
    ) -> None:
        """
        YoloWorker.on_result callback에서 호출한다.

        Incident 저장 실패가
        YoloWorker 자체 종료로 전파되지 않도록
        이 메서드 내부에서 예외를 처리한다.
        """

        try:

            selected = (
                self
                ._candidate_filter
                .select(
                    frame=frame,
                    detections=(
                        detections
                    ),
                )
            )

            verified_candidates = (
                self
                ._temporal_verifier
                .observe(
                    frame=frame,
                    detections_by_hazard=(
                        selected
                    ),
                )
            )

        except Exception as exc:

            print(
                "[INCIDENT PIPELINE ERROR] "
                "후보/시간 검증 실패 "
                f"/ cctv={frame.cctv_id} "
                f"/ error={exc}"
            )

            return

        for candidate in (
            verified_candidates
        ):

            self._register_candidate(
                candidate
            )

    def _register_candidate(
        self,
        candidate: IncidentCandidate,
    ) -> None:

        try:

            image_bytes = (
                self._encode_jpeg(
                    candidate.frame
                )
            )

            payload = {
                "cctv_id":
                    candidate.frame.cctv_id,

                "hazard_type":
                    candidate
                    .detection
                    .hazard_type,

                "confidence":
                    candidate
                    .detection
                    .confidence,

                "model_version":
                    candidate
                    .detection
                    .model_version,

                "detection_bbox_json":
                    self._bbox_to_json(
                        candidate
                        .detection
                        .bbox
                    ),

                "dedup_key":
                    candidate.dedup_key,

                "detected_at":
                    candidate
                    .frame
                    .captured_at,

                "representative_image":
                    image_bytes,
            }

            incident = (
                self._register_fn(
                    payload
                )
            )

            incident_id = (
                self._read_result_value(
                    incident,
                    "id",
                )
            )

            incident_no = (
                self._read_result_value(
                    incident,
                    "incident_no",
                )
            )

            print(
                "[INCIDENT UPSERT] "
                f"CCTV "
                f"{candidate.frame.cctv_id} "
                f"/ hazard="
                f"{candidate.detection.hazard_type} "
                f"/ duration="
                f"{candidate.duration_sec}s "
                f"/ confidence="
                f"{candidate.detection.confidence:.3f} "
                f"/ incident_id="
                f"{incident_id} "
                f"/ incident_no="
                f"{incident_no} "
                f"/ dedup="
                f"{candidate.dedup_key}"
            )

        except Exception as exc:

            print(
                "[INCIDENT PIPELINE ERROR] "
                "Incident 저장 실패 "
                f"/ cctv="
                f"{candidate.frame.cctv_id} "
                f"/ hazard="
                f"{candidate.detection.hazard_type} "
                f"/ error={exc}"
            )

    def _encode_jpeg(
        self,
        frame: Frame,
    ) -> bytes:

        if frame.image is None:

            raise ValueError(
                "Frame image가 없습니다."
            )

        success, encoded = (
            cv2.imencode(
                ".jpg",
                frame.image,
                [
                    int(
                        cv2.IMWRITE_JPEG_QUALITY
                    ),
                    int(
                        self
                        ._config
                        .jpeg_quality
                    ),
                ],
            )
        )

        if not success:

            raise RuntimeError(
                "대표 이미지 JPEG "
                "인코딩에 실패했습니다."
            )

        return encoded.tobytes()

    @staticmethod
    def _bbox_to_json(
        bbox: tuple[
            float,
            float,
            float,
            float,
        ],
    ) -> dict[str, float]:

        (
            x1,
            y1,
            x2,
            y2,
        ) = bbox

        return {
            "x1": float(x1),
            "y1": float(y1),
            "x2": float(x2),
            "y2": float(y2),
        }

    @staticmethod
    def _read_result_value(
        result: object,
        key: str,
    ) -> object | None:

        if isinstance(
            result,
            Mapping,
        ):
            return result.get(
                key
            )

        try:
            return result[
                key
            ]

        except Exception:
            return None