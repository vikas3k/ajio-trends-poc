"""Agent 2 - Trend Generator + Namer (PRD section 4 + 6).

Generates a trend catalogue from the three PRD data sources and names each trend
buzzword-first with 3-5 candidate names for human review:

  A. Grounded social/LLM research  -> live brief (PRD 6.2 LLM query + 6.3 crawl)
  B. Buzzword dictionary           -> current circulating buzzwords + what they
                                      map to (PRD 6.3)
  C. Attribute-driven trends       -> group Impetus combos, named buzzword-first
                                      (PRD 6.1 -> attribute_driven)
  D. Occasion/Event/Functional     -> LLM-generated for the current Indian
                                      calendar/events (PRD 6.2)

Grounding can't combine with a JSON schema, so A is free-text grounded; B/C/D are
structured calls that consume A.
"""
from __future__ import annotations

import datetime as _dt
import json
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from . import prompts
from .calendar import calendar_block
from .llm import grounded_call, structured_call
from .state import AgentState


class Buzzword(BaseModel):
    buzzword: str
    maps_to: str           # attributes / look it implies
    likely_category: str   # attribute_driven | occasion_festival | event_driven | functional
    recency: Literal["hot", "rising", "evergreen", "niche"]  # how live it is now
    confidence: Literal["high", "medium", "low"]             # how sure it's really circulating
    evidence: str          # where it's seen / why we believe it (from the live research)
    note: str


class AttributeTrend(BaseModel):
    candidate_names: list[str]      # 3-5, buzzword-first
    display_name: str               # the recommended one (a real buzzword if it fits)
    description: str
    rationale: str
    raw_signal: str                 # the underlying attribute combination
    matched_buzzword: str           # buzzword used, else ""
    member_combo_ids: list[int]


class ContextTrend(BaseModel):
    candidate_names: list[str]
    display_name: str
    category: Literal["occasion_festival", "event_driven", "functional"]
    description: str
    rationale: str
    raw_signal: str                 # the occasion/event/functional context signal
    validity_window: str            # e.g. "Oct-Nov 2026 (Diwali)"


MIN_TRENDS_PER_BUCKET = 10

_TOPWEAR = {"tops", "t-shirts", "shirts", "knitwear", "sweats/hoodies", "outerwear"}
_BOTTOMWEAR = {"trousers", "denim", "shorts", "joggers/knit bottoms", "leggings/tights", "skirts"}
_OTHERS = {"co-ords/sets", "dresses", "jumpsuits/rompers"}


def _parse_signal(raw_signal: str) -> dict[str, str]:
    result = {}
    for part in raw_signal.split(","):
        part = part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip().lower()] = v.strip()
    return result


def _garment_category(garment: str) -> str:
    g = garment.lower()
    if g in _TOPWEAR:
        return "topwear"
    if g in _BOTTOMWEAR:
        return "bottomwear"
    if g in _OTHERS:
        return "others"
    return "others"


def _check_bucket_coverage(
    trends: list[AttributeTrend],
    min_per_bucket: int = MIN_TRENDS_PER_BUCKET,
) -> None:
    """Log a warning for any gender × category bucket below the minimum."""
    counts: Counter = Counter()
    for t in trends:
        sig = _parse_signal(t.raw_signal)
        gender = sig.get("gender", "unknown")
        garment = sig.get("garment", "")
        category = _garment_category(garment)
        counts[(gender, category)] += 1
    for (gender, category), n in sorted(counts.items()):
        status = "OK" if n >= min_per_bucket else f"BELOW MINIMUM (got {n}, want {min_per_bucket})"
        print(f"[agent2] bucket {gender} × {category}: {n} trends — {status}")


def _landscape(records: list[dict]) -> str:
    def top(field, n=8):
        c = Counter()
        for r in records:
            if field in r and r[field] not in ("", "-"):
                c[r[field]] += r["count"]
        return ", ".join(f"{k} ({v})" for k, v in c.most_common(n))
    parts = []
    for f in ("gender", "garment", "color", "style", "pattern", "fabric"):
        if any(f in r for r in records):
            parts.append(f"{f}: {top(f)}")
    return "\n".join(parts)


def _grounded_brief(landscape: str, today: str, min_chars: int = 600, attempts: int = 3) -> str:
    base = prompts.fmt("agent2.research", today=today, landscape=landscape)
    best = ""
    for attempt in range(1, attempts + 1):
        try:
            b = grounded_call(base, system=prompts.get("agent2.research_system"),
                             name=f"agent2_grounded_research_{attempt}")
        except Exception as e:
            print(f"[agent2] grounding unavailable ({e}); curated brief only")
            return best or "(live grounding unavailable; relying on curated brief)"
        if len(b) > len(best):
            best = b
        if len(b) >= min_chars:
            return b
        print(f"[agent2] grounding short ({len(b)}), retry {attempt}/{attempts}")
        base += prompts.get("agent2.research_retry_suffix")
    return best


def run(state: AgentState, max_combos: int = 400) -> AgentState:
    records = state["cleaned_records"]
    today = _dt.date.today().isoformat()

    # A. Grounded social/LLM research (PRD 6.2 + 6.3).
    landscape = _landscape(records)
    brief = _grounded_brief(landscape, today)
    print(f"[agent2] grounded research: {len(brief)} chars")

    # B. Buzzword dictionary (PRD 6.3).
    buzz = structured_call(
        prompts.fmt("agent2.buzzword_extract", brief=brief),
        list[Buzzword], system=prompts.get("agent2.buzzword_system"),
        name="agent2_buzzword_dictionary", temperature=0.3,
    ) or []
    buzz_dicts = [b.model_dump() for b in buzz]
    buzz_lines = "\n".join(
        f"- {b.buzzword} -> {b.maps_to} [{b.likely_category}; {b.recency}, {b.confidence}-confidence]"
        for b in buzz
    )
    print(f"[agent2] buzzword dictionary: {len(buzz_dicts)} buzzwords")

    # C. Attribute-driven trends from Impetus combos (PRD 6.1), buzzword-first.
    combos = records[:max_combos]
    attr_prompt = prompts.fmt(
        "agent2.attribute_trends", buzz_lines=buzz_lines,
        combos_json=json.dumps(combos, ensure_ascii=False, indent=1),
    )
    attr_trends = structured_call(
        attr_prompt, list[AttributeTrend], system=prompts.get("agent2.attr_system"),
        name="agent2_attribute_trends", temperature=0.6,
    ) or []
    _check_bucket_coverage(attr_trends)
    print(f"[agent2] attribute_driven trends: {len(attr_trends)}")

    # D. Occasion/Event/Functional trends from live context (PRD 6.2).
    calendar = calendar_block(today=_dt.date.today())
    print(f"[agent2] calendar block: {calendar.count(chr(10))+1} events injected")
    ctx_prompt = prompts.fmt(
        "agent2.context_trends", today=today, brief=brief,
        buzz_lines=buzz_lines, calendar=calendar,
    )
    ctx_trends = structured_call(
        ctx_prompt, list[ContextTrend], system=prompts.get("agent2.context_system"),
        name="agent2_context_trends", temperature=0.6,
    ) or []
    print(f"[agent2] occasion/event/functional trends: {len(ctx_trends)}")

    # Combine into a uniform pre-classification trend list.
    trends = []
    for t in attr_trends:
        d = t.model_dump()
        trends.append({
            "display_name": d["display_name"],
            "candidate_names": d["candidate_names"],
            "description": d["description"],
            "rationale": d["rationale"],
            "raw_signal": d["raw_signal"],
            "source": "social_crawl" if d.get("matched_buzzword") else "impetus",
            "matched_buzzword": d.get("matched_buzzword", ""),
            "provisional_category": "attribute_driven",
            "member_combo_ids": d.get("member_combo_ids", []),
            "validity_window": "",
        })
    for t in ctx_trends:
        d = t.model_dump()
        trends.append({
            "display_name": d["display_name"],
            "candidate_names": d["candidate_names"],
            "description": d["description"],
            "rationale": d["rationale"],
            "raw_signal": d["raw_signal"],
            "source": "llm",
            "matched_buzzword": "",
            "provisional_category": d["category"],
            "member_combo_ids": [],
            "validity_window": d.get("validity_window", ""),
        })

    print(f"[agent2] total trends generated: {len(trends)}")
    return {"trend_brief": brief, "buzzwords": buzz_dicts, "trends": trends}
