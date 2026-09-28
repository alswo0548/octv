"""AI 단계 사이의 데이터 형식 초안. DB의 실제 ID와 원본 단위를 사용하세요."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Frame:
    cctv_id: int
    captured_at: datetime
    image_path: str


@dataclass(frozen=True)
class Detection:
    hazard_type: str
    confidence: float  # 0~1. UI의 백분율은 표시할 때 변환합니다.
    bbox: tuple[float, float, float, float]  # TODO: 좌표 기준을 팀과 합의하세요.
    model_version: str


@dataclass(frozen=True)
class IncidentCandidate:
    frame: Frame
    detection: Detection
    duration_sec: int
    dedup_key: str


@dataclass(frozen=True)
class ContextSnapshot:
    incident_id: int
    captured_at: datetime
    measurements: dict
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Assessment:
    risk_score: float
    priority: str
    breakdown: dict
    rule_version: str
