"""Route real YOLO predictions by CCTV ID without changing the teammate's worker.

DEMO model selections are read from the explicit approved v5 mapping. The
existing IncidentPipeline performs time validation and creates Incidents.
The approved HTML's 1-second/80% display filter is NOT applied here: the
production sampler/VERIFY policy has different timing and requires rehearsal.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ai.contracts import Detection, Frame

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "demo" / "videos" / "_v5" / "weights"
MAPPING_FILE = ROOT / "demo" / "videos" / "_v5" / "OCTV_v5_연결표.json"


@dataclass(frozen=True)
class DemoRoute:
    external_id: str
    model_name: str
    target_hazard: str
    entry_conf: float
    keep_conf: float


# Validated against the review/acceptance JSON, not inferred from filenames.
APPROVED_ROUTES = (
    DemoRoute("DEMO-N001", "N052_S2_epoch005.pt", "flood", 0.80, 0.50),
    DemoRoute("DEMO-N002", "Cycle7.pt", "flood", 0.68, 0.68),
    DemoRoute("DEMO-N003", "L_last.pt", "fallen_tree", 0.55, 0.55),
)


def read_demo_id_map(connection: Any) -> dict[str, int]:
    """Resolve IDs from this database; never rely on today's 4/5/6 PKs."""
    names = [route.external_id for route in APPROVED_ROUTES]
    rows = connection.execute(
        "SELECT id, external_cctv_id FROM cctvs "
        "WHERE provider = %s AND external_cctv_id = ANY(%s)",
        ("DEMO", names),
    ).fetchall()
    mapped = {
        str(row["external_cctv_id"] if isinstance(row, Mapping) else row[1]):
        int(row["id"] if isinstance(row, Mapping) else row[0])
        for row in rows
    }
    if set(mapped) != set(names) or len(set(mapped.values())) != len(names):
        raise RuntimeError("Demo CCTV 3대 ID 매핑 실패: " + repr(mapped))
    return mapped



# Approved SHA-256 from OCTV_v5_user_acceptance.json, independently verified
# during the preparation stage. Never accept a silently replaced demo model.
APPROVED_HASHES = {
    "weights/Cycle7.pt": "d886463b48f87125853d6ab45a8a145e7584e0afb908fdf76a5c5220eea2d02b",
    "weights/N052_S2_epoch005.pt": "ab075d5195663b83904ccef638bab51450048c8313aaa3c4b486eeee0ce971eb",
    "weights/L_last.pt": "e5f8d4d7297b0a362012a97e0fecf430ee9961a5623df5fbf4370ec143882cf7",
    "../N001_demo.mp4": "2faf44b26bc4afe45c962bfdce3e9647d69828787cf787a25f4a737e67310f6b",
    "../N002_demo.mp4": "e91802b79eec1cae14df418bde118822f651729732d5472a12866490d866af4f",
    "../N003_demo.mp4": "5086ceb914503a581494f1ca09ef9a5869b1464f4c70f874994b33f2d3b754e4",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_approved_files() -> None:
    """Fail closed for missing/mismatched scene config and model files."""
    paths = [MODELS_DIR / route.model_name for route in APPROVED_ROUTES]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError("승인 v5 가중치가 없습니다: " + ", ".join(missing))

    videos = {"N001_demo.mp4", "N002_demo.mp4", "N003_demo.mp4"}
    missing_videos = [name for name in sorted(videos) if not (ROOT / "demo/videos" / name).is_file()]
    if missing_videos:
        raise FileNotFoundError("승인 Demo 영상이 없습니다: " + ", ".join(missing_videos))

    for relative, expected_sha in APPROVED_HASHES.items():
        path = (MODELS_DIR.parent / relative).resolve()
        if _sha256(path) != expected_sha:
            raise RuntimeError("승인 파일 SHA256 불일치: " + str(path))

    scenario = json.loads((ROOT / "demo/scenarios.json").read_text(encoding="utf-8"))
    cases = scenario["main_demo"]["cases"]
    expected = {"DEMO-N001": "N001_demo.mp4", "DEMO-N003": "N003_demo.mp4"}
    found = {case["external_cctv_id"]: case["video"] for case in cases}
    if found != expected or any(case.get("provider", "").upper() != "DEMO" for case in cases):
        raise RuntimeError("demo/scenarios.json의 승인 시연 2개 대응이 올바르지 않습니다.")


class DemoModelRouter:
    """Keep standard UTIC predictions unchanged; use special models for Demo."""

    def __init__(
        self,
        base_detector: Any,
        routes_by_id: Mapping[int, tuple[DemoRoute, Any]],
    ) -> None:
        self.base_detector = base_detector
        self.routes_by_id = dict(routes_by_id)

    def detect(self, frame: Frame) -> list[Detection]:
        route_pair = self.routes_by_id.get(frame.cctv_id)
        if route_pair is None:
            # For UTIC, preserve original model class predictions and pipeline.
            return self.base_detector.detect(frame)
        route, detector = route_pair
        predictions = detector.detect(frame)
        # This is actual model inference: no prerecorded Incident, bbox, or score.
        # The integration uses the v5 entry threshold on OCTV's sampled frames.
        # HTML's separate 1s/80% temporal presentation remains unimplemented.
        return [
            det for det in predictions
            if det.hazard_type == route.target_hazard
            and det.confidence >= route.entry_conf
        ]


def build_router(
    base_detector: Any,
    connection: Any,
    *,
    yolo_factory: Callable[..., Any],
    imgsz: int,
    device: str,
) -> DemoModelRouter:
    validate_approved_files()
    ids = read_demo_id_map(connection)
    routes: dict[int, tuple[DemoRoute, Any]] = {}
    # Demo N002's approved model and asset hashes remain available for rollback,
    # but the lightweight rehearsal only loads/runs the two scenario models.
    scenario = json.loads((ROOT / "demo/scenarios.json").read_text(encoding="utf-8"))
    active_demo_ids = {case["external_cctv_id"] for case in scenario["main_demo"]["cases"]}
    detectors_by_path: dict[Path, Any] = {Path(base_detector.model_path).resolve(): base_detector}
    for route in APPROVED_ROUTES:
        if route.external_id not in active_demo_ids:
            continue
        path = (MODELS_DIR / route.model_name).resolve()
        detector = detectors_by_path.get(path)
        if detector is None:
            detector = yolo_factory(
                model_path=path,
                imgsz=imgsz,
                device=device,
                confidence=route.keep_conf,
            )
            detector.warmup()
            detectors_by_path[path] = detector
        # The base detector may have a lower internal confidence; entry filter
        # above is always applied. This also preserves the base UTIC threshold.
        if detector is base_detector and detector.confidence > route.entry_conf:
            raise RuntimeError("기존 YOLO confidence가 Demo 진입 임계값보다 높습니다.")
        routes[ids[route.external_id]] = (route, detector)
        print(f"[V5 ROUTER] id={ids[route.external_id]} {route.external_id} "
              f"model={route.model_name} target={route.target_hazard} entry={route.entry_conf}")
    return DemoModelRouter(base_detector, routes)
