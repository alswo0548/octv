"""YOLO Detection을 시간 검증한 뒤 Incident로 저장하는 Pipeline."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    YOLO 결과 → 위험 후보 → 시간 검증 → Incident 확정 설정.

    candidate_confidence_threshold:
        YOLO 결과를 위험 후보로 추적하기 시작할 최소 confidence.

    min_area_ratio:
        전체 Frame 대비 bbox 최소 면적 비율.

    candidate_min_detection_count:
        검증 시간창 안에서 동일 hazard가
        탐지되어야 하는 최소 횟수.

    temporal_validation_sec:
        첫 후보 탐지 후 반복 탐지를 확인하는
        최대 검증 시간창(초).

        재난이 이 시간 동안 계속 보여야 한다는 뜻이 아니다.

    incident_confidence_threshold:
        검증 시간창 안의 탐지 중 최소 한 번은
        이 confidence 이상이어야 Incident로 확정할 수 있다.

    track_ttl_sec:
        오랫동안 갱신되지 않은 임시 후보 Track 제거 시간.

    jpeg_quality:
        사건 대표 이미지 JPEG 품질.
    """

    candidate_confidence_threshold: float = 0.35
    min_area_ratio: float = 0.0005

    candidate_min_detection_count: int = 3
    temporal_validation_sec: float = 15.0
    incident_confidence_threshold: float = 0.35

    temporal_min_iou: float = 0.20

    track_ttl_sec: float = 60.0

    jpeg_quality: int = 90

    def __post_init__(self) -> None:

        if not 0.0 <= self.candidate_confidence_threshold <= 1.0:
            raise ValueError(
                "candidate_confidence_threshold는 "
                "0~1이어야 합니다."
            )

        if not 0.0 <= self.incident_confidence_threshold <= 1.0:
            raise ValueError(
                "incident_confidence_threshold는 "
                "0~1이어야 합니다."
            )

        if (
            self.incident_confidence_threshold
            < self.candidate_confidence_threshold
        ):
            raise ValueError(
                "incident_confidence_threshold는 "
                "candidate_confidence_threshold보다 "
                "작을 수 없습니다."
            )

        if not 0.0 <= self.min_area_ratio <= 1.0:
            raise ValueError(
                "min_area_ratio는 0~1이어야 합니다."
            )

        if self.candidate_min_detection_count <= 0:
            raise ValueError(
                "candidate_min_detection_count는 "
                "1 이상이어야 합니다."
            )

        if self.temporal_validation_sec <= 0:
            raise ValueError(
                "temporal_validation_sec은 "
                "0보다 커야 합니다."
            )

        if not 0.0 <= self.temporal_min_iou <= 1.0:
            raise ValueError(
                "temporal_min_iou는 0~1이어야 합니다."
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
    def from_settings(
        cls,
        settings: Mapping[str, object],
    ) -> "IncidentPipelineConfig":
        """
        monitoring_settings DB 값을
        Incident Pipeline 설정으로 변환한다.

        DB에서 관리하는 Incident 정책은 DB 값을 우선하고,
        DB에 없는 Runtime 세부값은 기존 ENV 설정을 유지한다.
        """

        fallback = cls.from_env()

        return cls(
            candidate_confidence_threshold=float(
                settings[
                    "candidate_confidence_threshold"
                ]
            ),
            min_area_ratio=(
                fallback.min_area_ratio
            ),
            candidate_min_detection_count=int(
                settings[
                    "candidate_min_detection_count"
                ]
            ),
            temporal_validation_sec=float(
                settings[
                    "temporal_validation_sec"
                ]
            ),
            incident_confidence_threshold=float(
                settings[
                    "incident_confidence_threshold"
                ]
            ),
            temporal_min_iou=(
                fallback.temporal_min_iou
            ),
            track_ttl_sec=(
                fallback.track_ttl_sec
            ),
            jpeg_quality=(
                fallback.jpeg_quality
            ),
        )

    @classmethod
    def from_env(
        cls,
    ) -> "IncidentPipelineConfig":
        """
        DB 설정을 주입하지 않는 테스트/독립 실행용 fallback.
        """

        candidate_threshold = float(
            os.getenv(
                "OCTV_CANDIDATE_MIN_CONFIDENCE",
                "0.35",
            )
        )

        return cls(
            candidate_confidence_threshold=(
                candidate_threshold
            ),
            min_area_ratio=float(
                os.getenv(
                    "OCTV_CANDIDATE_MIN_AREA_RATIO",
                    "0.0005",
                )
            ),
            candidate_min_detection_count=int(
                os.getenv(
                    "OCTV_TEMPORAL_MIN_HITS",
                    "3",
                )
            ),
            temporal_validation_sec=float(
                os.getenv(
                    "OCTV_TEMPORAL_VALIDATION_SEC",
                    "15",
                )
            ),
            incident_confidence_threshold=float(
                os.getenv(
                    "OCTV_INCIDENT_CONFIDENCE_THRESHOLD",
                    str(candidate_threshold),
                )
            ),
            temporal_min_iou=float(
                os.getenv(
                    "OCTV_TEMPORAL_MIN_IOU",
                    "0.20",
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
                < self._config.candidate_confidence_threshold
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


@dataclass
class _TemporalTrack:
    """
    CCTV + hazard 단위의 시간 검증 상태.

    verified = False
        아직 Incident로 확정되지 않은 VERIFY 후보.

    verified = True
        이미 Incident 저장까지 성공한 위험상황.
        같은 위험이 계속 보이면 같은 dedup_key로
        Incident를 갱신한다.
    """

    first_positive_at: datetime

    last_positive_at: datetime

    last_sample_at: datetime

    hit_count: int = 1

    last_bbox: tuple[float, float, float, float] | None = None

    verified: bool = False


# =========================================================
# Temporal Verifier
# =========================================================


class TemporalIncidentVerifier:
    """
    최초 후보 탐지 이후 제한된 검증 시간 안에
    동일 hazard가 반복 탐지되는지 확인한다.

    기본 정책:

        후보 최초 탐지
            ↓
        최대 15초 VERIFY
            ↓
        동일 hazard 3회 탐지
            ↓
        Incident 후보 확정

    예:

        t=0   O  → 1회
        t=2   X
        t=4   O  → 2회
        t=6   X
        t=8   O  → 3회

        → 8초 시점에서 즉시 검증 성공.

    15초 동안 계속 탐지되어야 한다는 뜻이 아니다.

    검증 실패:

        최초 후보 이후 temporal_validation_sec을
        초과했는데 최소 탐지 횟수를 충족하지 못하면
        이전 후보 세션을 종료한다.

    이미 검증된 Track:

        검증 성공 이후 같은 hazard가 계속 보이면
        추가 Temporal 검증 없이 Incident 갱신 후보로
        반환한다.

        일정 시간 동안 다시 탐지되지 않으면
        Track을 제거하고 이후 탐지는 새 후보로 시작한다.
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

    # =====================================================
    # Frame 관측
    # =====================================================

    def observe(
        self,
        frame: Frame,
        detections_by_hazard: Mapping[
            str,
            Detection,
        ],
    ) -> list[IncidentCandidate]:

        self._cleanup_stale_tracks(
            current_at=frame.captured_at
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

        candidates: list[
            IncidentCandidate
        ] = []

        for hazard_type in sorted(
            observed_hazards
        ):

            key = (
                cctv_id,
                hazard_type,
            )

            detection = (
                detections_by_hazard.get(
                    hazard_type
                )
            )

            track = (
                self._tracks.get(
                    key
                )
            )

            # =================================================
            # 새 후보 Track
            # =================================================

            if track is None:

                if detection is None:
                    continue

                track = _TemporalTrack(
                    first_positive_at=(
                        frame.captured_at
                    ),
                    last_positive_at=(
                        frame.captured_at
                    ),
                    last_sample_at=(
                        frame.captured_at
                    ),
                    hit_count=1,
                    last_bbox=detection.bbox,
                    verified=False,
                )

                self._tracks[
                    key
                ] = track

                self._print_pending(
                    cctv_id=cctv_id,
                    hazard_type=hazard_type,
                    track=track,
                    detection=detection,
                )

                # 최소 횟수가 1로 설정된 특수한 경우도
                # 정상 처리할 수 있도록 아래 검증으로 진행한다.

            else:

                # 이미 처리한 Frame 또는
                # 더 오래된 Frame은 무시한다.
                if (
                    frame.captured_at
                    <= track.last_sample_at
                ):
                    continue

                track.last_sample_at = (
                    frame.captured_at
                )

                # =============================================
                # 이미 Incident로 확정된 Track
                # =============================================

                if track.verified:

                    if detection is None:

                        gap_sec = (
                            frame.captured_at
                            - track.last_positive_at
                        ).total_seconds()

                        # 일정 시간 동안 위험이 다시
                        # 보이지 않으면 기존 위험 구간 종료.
                        if (
                            gap_sec
                            > self._config
                            .temporal_validation_sec
                        ):

                            self._tracks.pop(
                                key,
                                None,
                            )

                            print(
                                "[TEMPORAL] "
                                f"CCTV {cctv_id} "
                                f"/ hazard={hazard_type} "
                                "/ confirmed track 종료 "
                                f"/ no_detection="
                                f"{gap_sec:.1f}s"
                            )

                        continue

                    track.last_positive_at = (
                        frame.captured_at
                    )

                    duration_sec = (
                        self._duration_sec(
                            start=(
                                track
                                .first_positive_at
                            ),
                            end=(
                                frame.captured_at
                            ),
                        )
                    )

                    candidates.append(
                        self._build_candidate(
                            frame=frame,
                            detection=detection,
                            duration_sec=(
                                duration_sec
                            ),
                        )
                    )

                    continue

                # =============================================
                # 아직 검증 중인 Track
                # =============================================

                elapsed_sec = (
                    frame.captured_at
                    - track.first_positive_at
                ).total_seconds()

                if (
                    elapsed_sec
                    > self._config
                    .temporal_validation_sec
                ):

                    self._tracks.pop(
                        key,
                        None,
                    )

                    print(
                        "[TEMPORAL] "
                        f"CCTV {cctv_id} "
                        f"/ hazard={hazard_type} "
                        "/ VERIFY 실패 "
                        f"/ elapsed="
                        f"{elapsed_sec:.1f}s "
                        f"/ hits="
                        f"{track.hit_count}"
                    )

                    # 현재 Frame에 Detection이 있더라도
                    # 같은 VERIFY 세션을 즉시 연장하지 않는다.
                    #
                    # Runtime이 먼저 원래 BASE / ALERT로 복귀하고,
                    # 이후 일반 감시 상태에서 다시 후보가 탐지되면
                    # 그때 새로운 VERIFY 세션을 시작한다.
                    continue

                elif detection is not None:

                    bbox_iou = self._bbox_iou(
                        track.last_bbox,
                        detection.bbox,
                    )

                    if (
                        bbox_iou
                        < self._config.temporal_min_iou
                    ):
                        print(
                            "[TEMPORAL] "
                            f"CCTV {cctv_id} "
                            f"/ hazard={hazard_type} "
                            "/ bbox 불일치 → hit 누적 재시작 "
                            f"/ iou={bbox_iou:.3f} "
                            f"/ required="
                            f"{self._config.temporal_min_iou:.3f}"
                        )

                        # 서로 다른 위치의 같은 hazard는
                        # 동일 객체의 연속 탐지로 누적하지 않는다.
                        #
                        # 단, VERIFY 전체 제한시간은 최초 후보
                        # 탐지 시점부터 계속 유지한다.
                        # bbox가 바뀌었다는 이유로
                        # first_positive_at을 갱신하면
                        # VERIFY가 무한 연장될 수 있다.
                        track.last_positive_at = (
                            frame.captured_at
                        )
                        track.last_sample_at = (
                            frame.captured_at
                        )
                        track.hit_count = 1
                        track.last_bbox = (
                            detection.bbox
                        )

                    else:
                        track.last_positive_at = (
                            frame.captured_at
                        )
                        track.last_bbox = (
                            detection.bbox
                        )
                        track.hit_count += 1

            # =================================================
            # 현재 Frame 미탐
            # =================================================

            if detection is None:
                continue

            self._print_pending(
                cctv_id=cctv_id,
                hazard_type=hazard_type,
                track=track,
                detection=detection,
            )

            # =================================================
            # 최소 반복 탐지 횟수
            # =================================================

            if (
                track.hit_count
                < self._config
                .candidate_min_detection_count
            ):
                continue

            # =================================================
            # Incident 확정 confidence
            # =================================================

            if (
                detection.confidence
                < self._config
                .incident_confidence_threshold
            ):

                print(
                    "[TEMPORAL] "
                    "탐지 횟수 충족 / "
                    "Incident confidence 미달 "
                    f"/ cctv={cctv_id} "
                    f"/ hazard={hazard_type} "
                    f"/ confidence="
                    f"{detection.confidence:.3f} "
                    f"/ required="
                    f"{self._config.incident_confidence_threshold:.3f}"
                )

                continue

            duration_sec = (
                self._duration_sec(
                    start=(
                        track.first_positive_at
                    ),
                    end=(
                        frame.captured_at
                    ),
                )
            )

            candidates.append(
                self._build_candidate(
                    frame=frame,
                    detection=detection,
                    duration_sec=(
                        duration_sec
                    ),
                )
            )

        return candidates

    # =====================================================
    # Incident 저장 성공 통지
    # =====================================================

    def mark_verified(
        self,
        cctv_id: int,
        hazard_type: str,
    ) -> None:
        """
        Incident DB 저장이 실제 성공한 뒤 호출한다.

        DB 저장 실패인데 Track만 verified 처리되는 것을
        방지하기 위해 observe() 내부에서 바로 확정하지 않는다.
        """

        key = (
            int(cctv_id),
            str(hazard_type),
        )

        track = (
            self._tracks.get(
                key
            )
        )

        if track is None:
            return

        track.verified = True

    # =====================================================
    # 현재 VERIFY 중인 hazard
    # =====================================================

    def pending_hazards(
        self,
        cctv_id: int,
    ) -> tuple[str, ...]:
        """
        아직 Incident DB 저장에 성공하지 않은
        Temporal 후보만 반환한다.

        Runtime은 이 값이 하나라도 있으면
        CCTV를 VERIFY 모드로 유지한다.
        """

        target_id = int(
            cctv_id
        )

        return tuple(
            sorted(
                hazard_type
                for (
                    track_cctv_id,
                    hazard_type,
                ),
                track
                in self._tracks.items()
                if (
                    track_cctv_id
                    == target_id
                    and not track.verified
                )
            )
        )

    # =====================================================
    # Candidate 생성
    # =====================================================

    @staticmethod
    def _build_candidate(
        frame: Frame,
        detection: Detection,
        duration_sec: int,
    ) -> IncidentCandidate:

        return IncidentCandidate(
            frame=frame,
            detection=detection,
            duration_sec=(
                duration_sec
            ),
            dedup_key=(
                TemporalIncidentVerifier
                ._build_dedup_key(
                    cctv_id=(
                        int(
                            frame.cctv_id
                        )
                    ),
                    hazard_type=(
                        detection
                        .hazard_type
                    ),
                )
            ),
        )

    @staticmethod
    def _build_dedup_key(
        cctv_id: int,
        hazard_type: str,
    ) -> str:

        return (
            f"cctv:{cctv_id}:"
            f"hazard:{hazard_type}"
        )


    @staticmethod
    def _bbox_iou(
        first_bbox: tuple[
            float,
            float,
            float,
            float,
        ] | None,
        second_bbox: tuple[
            float,
            float,
            float,
            float,
        ],
    ) -> float:

        if first_bbox is None:
            return 0.0

        ax1, ay1, ax2, ay2 = first_bbox
        bx1, by1, bx2, by2 = second_bbox

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_width = max(
            0.0,
            inter_x2 - inter_x1,
        )
        inter_height = max(
            0.0,
            inter_y2 - inter_y1,
        )

        intersection = (
            inter_width
            * inter_height
        )

        first_area = max(
            0.0,
            ax2 - ax1,
        ) * max(
            0.0,
            ay2 - ay1,
        )

        second_area = max(
            0.0,
            bx2 - bx1,
        ) * max(
            0.0,
            by2 - by1,
        )

        union = (
            first_area
            + second_area
            - intersection
        )

        if union <= 0.0:
            return 0.0

        return (
            intersection
            / union
        )


    @staticmethod
    def _duration_sec(
        start: datetime,
        end: datetime,
    ) -> int:

        return max(
            0,
            int(
                (
                    end
                    - start
                ).total_seconds()
            ),
        )

    def _print_pending(
        self,
        cctv_id: int,
        hazard_type: str,
        track: _TemporalTrack,
        detection: Detection,
    ) -> None:

        elapsed_sec = (
            track.last_sample_at
            - track.first_positive_at
        ).total_seconds()

        print(
            "[TEMPORAL] "
            f"CCTV {cctv_id} "
            f"/ hazard={hazard_type} "
            f"/ hits={track.hit_count}"
            f"/ required="
            f"{self._config.candidate_min_detection_count} "
            f"/ elapsed="
            f"{elapsed_sec:.1f}s"
            f"/ limit="
            f"{self._config.temporal_validation_sec:.1f}s "
            f"/ confidence="
            f"{detection.confidence:.3f}"
        )

    # =====================================================
    # 장시간 갱신되지 않은 Track 정리
    # =====================================================

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
# Pipeline 실행 결과
# =========================================================


@dataclass(frozen=True)
class IncidentPipelineResult:
    """
    CCTV Runtime이 VERIFY 상태를 제어하기 위한 결과.

    pending_hazards:
        아직 15초 Temporal 검증 중인 hazard.

    registered_hazards:
        이번 Frame에서 Incident 저장에 성공한 hazard.

    had_error:
        후보 필터/Temporal 처리 자체에 오류가 발생했는지 여부.
    """

    pending_hazards: tuple[
        str,
        ...
    ] = ()

    registered_hazards: tuple[
        str,
        ...
    ] = ()

    had_error: bool = False


# =========================================================
# Incident Pipeline
# =========================================================


class IncidentPipeline:
    """
    YOLO 결과를 Incident 저장까지 연결한다.

    흐름:

    Detection
        ↓
    OCTV hazard class 확인
        ↓
    candidate confidence / bbox filter
        ↓
    Temporal Verification
        최초 후보 후 최대 설정 시간 동안 재검증
        ↓
    동일 hazard 최소 횟수 충족
        ↓
    IncidentCandidate
        ↓
    JPEG encode
        ↓
    incidents.service.register_detection()
        ↓
    새 Incident INSERT
    또는 기존 진행 Incident UPSERT
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
            f"/ candidate_confidence>="
            f"{self._config.candidate_confidence_threshold:.2f} "
            f"/ incident_confidence>="
            f"{self._config.incident_confidence_threshold:.2f} "
            f"/ area_ratio>="
            f"{self._config.min_area_ratio:.6f} "
            f"/ temporal="
            f"{self._config.candidate_min_detection_count}"
            f" hits/"
            f"{self._config.temporal_validation_sec:.1f}s"
        )

    # =====================================================
    # YOLO Result
    # =====================================================

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
    ) -> IncidentPipelineResult:
        """
        YoloWorker.on_result callback에서 호출한다.

        Incident 저장 실패가
        YoloWorker Thread 종료로 전파되지 않도록
        내부에서 처리한다.
        """

        cctv_id = int(
            frame.cctv_id
        )

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

            candidates = (
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
                f"/ cctv={cctv_id} "
                f"/ error={exc}"
            )

            return IncidentPipelineResult(
                pending_hazards=(
                    self
                    ._temporal_verifier
                    .pending_hazards(
                        cctv_id
                    )
                ),
                had_error=True,
            )

        registered_hazards: set[
            str
        ] = set()

        for candidate in candidates:

            registered = (
                self._register_candidate(
                    candidate
                )
            )

            if not registered:
                continue

            hazard_type = (
                candidate
                .detection
                .hazard_type
            )

            registered_hazards.add(
                hazard_type
            )

            self._temporal_verifier.mark_verified(
                cctv_id=cctv_id,
                hazard_type=(
                    hazard_type
                ),
            )

        return IncidentPipelineResult(
            pending_hazards=(
                self
                ._temporal_verifier
                .pending_hazards(
                    cctv_id
                )
            ),
            registered_hazards=(
                tuple(
                    sorted(
                        registered_hazards
                    )
                )
            ),
            had_error=False,
        )

    # =====================================================
    # Incident DB 저장
    # =====================================================

    def _register_candidate(
        self,
        candidate: IncidentCandidate,
    ) -> bool:

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

            return True

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

            return False

    # =====================================================
    # JPEG
    # =====================================================

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

    # =====================================================
    # BBox
    # =====================================================

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

    # =====================================================
    # Repository 결과 읽기
    # =====================================================

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