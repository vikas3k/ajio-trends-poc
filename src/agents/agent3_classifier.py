"""Agent 3 - Trend Classifier (PRD section 3 taxonomy).

Assigns each trend exactly one of the PRD's four categories:
  - attribute_driven  : derived from product attributes (print, silhouette,
                        colour, fabric, fit). The base layer. e.g. Florals,
                        Wide-leg Trousers, Butter Yellow, Linen.
  - occasion_festival : tied to recurring cultural occasions / festivals / wedding
                        season (cyclic, predictable). e.g. Diwali, Durga Puja,
                        Raksha Bandhan, Eid, Christmas.
  - event_driven      : non-cyclic, unpredictable events - sport, celebrity,
                        fashion weeks, viral/OTT moments. e.g. FIFA jerseys,
                        Lakme Fashion Week, celeb-worn styles, OTT drops.
  - functional        : use-case / life-moment driven, spanning categories.
                        e.g. Back to College, Monsoon Ready, Work from Office,
                        Resort Ready, Airport Look.

Agent 2 attaches a provisional_category; Agent 3 confirms or corrects it so every
trend carries a clean, consistent PRD category.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from . import prompts
from .llm import structured_call
from .state import AgentState

Category = Literal["attribute_driven", "occasion_festival", "event_driven", "functional"]


class TrendClass(BaseModel):
    index: int
    category: Category
    reason: str


def run(state: AgentState) -> AgentState:
    trends = state["trends"]
    payload = [
        {
            "index": i,
            "name": t["display_name"],
            "description": t.get("description", ""),
            "raw_signal": t.get("raw_signal", ""),
            "provisional_category": t.get("provisional_category", ""),
        }
        for i, t in enumerate(trends)
    ]
    prompt = prompts.fmt("agent3.classify",
                         payload_json=json.dumps(payload, ensure_ascii=False, indent=1))
    results: list[TrendClass] = structured_call(
        prompt, list[TrendClass], system=prompts.get("agent3.system"),
        name="agent3_classify", temperature=0.1,
    ) or []
    by_index = {r.index: r for r in results}

    classified = []
    for i, t in enumerate(trends):
        r = by_index.get(i)
        classified.append({
            **t,
            "trend_category": r.category if r else (t.get("provisional_category") or "attribute_driven"),
            "category_reason": r.reason if r else "",
        })
    counts = {}
    for c in classified:
        counts[c["trend_category"]] = counts.get(c["trend_category"], 0) + 1
    print(f"[agent3] classified {len(classified)} trends -> {counts}")
    return {"classified_trends": classified}
