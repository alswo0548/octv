"""Read-only, control-room-only traffic simulations for OCTV demo.

Never alter the actual route candidate, MCP result, or navigation authorization.
A scenario is visibly synthetic and is applied only while the demo is running.
"""
from __future__ import annotations

from typing import Any

DEMO_INCIDENT_IDS = frozenset({4, 5, 19})


def overlay_candidates(incident_id: int, candidates: list[Any]) -> list[dict[str, Any]]:
    """Return presentation-only copies; never write these to the database."""
    copies = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in candidates]
    if incident_id not in DEMO_INCIDENT_IDS or len(copies) < 2:
        return copies

    # Apply stable examples to the saved API order. Do not assert a real road closure.
    eligible = [
        index for index, item in enumerate(copies)
        if item.get("disqualify_reason") is None
        and item.get("verification_status") != "DISQUALIFIED"
    ]
    if len(eligible) < 2:
        return copies

    blocked_index = eligible[0] if len(eligible) >= 3 else None
    delayed_index = eligible[1] if blocked_index is not None else eligible[0]

    if blocked_index is not None:
        item = copies[blocked_index]
        item["demo_traffic"] = {
            "type": "SIMULATED_FULL_CLOSURE",
            "label": "시연용 가상 전면 통제",
            "reason": "가상의 전면 통제 상황을 적용해 이 후보를 시연 중 제외합니다.",
            "simulated": True,
        }
        item["navigation_available"] = False
        item["requires_review"] = True
        item["demo_rank_status"] = "EXCLUDED"

    item = copies[delayed_index]
    item["demo_traffic"] = {
        "type": "SIMULATED_DELAY",
        "label": "시연용 가상 공사·정체",
        "reason": "가상의 공사·정체로 이 후보의 우선순위를 낮췄습니다. 실제 이동시간·점수는 변경하지 않습니다.",
        "simulated": True,
    }
    item["demo_rank_status"] = "DEPRIORITIZED"

    for index in eligible:
        if copies[index].get("demo_rank_status") is None:
            copies[index]["demo_rank_status"] = "UNCHANGED"
    return sorted(
        copies,
        key=lambda item: {"UNCHANGED": 0, "DEPRIORITIZED": 1, "EXCLUDED": 2}.get(
            item.get("demo_rank_status"), 0
        ),
    )
