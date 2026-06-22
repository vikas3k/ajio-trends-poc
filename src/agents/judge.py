"""LLM-as-judge: evaluates candidate trend names against PRD naming criteria.

Runs after Agent 3 (classification), before human review. For each trend,
scores every candidate name on 5 criteria, picks the best one as the
recommended name, and flags weak candidates so reviewers focus attention.

Uses gemini-2.5-flash (fast, cheap) via the same Vertex AI client — set
JUDGE_MODEL env var to override.

Output fields added to each trend:
  judge_recommended   — best candidate name by overall score
  judge_scores        — JSON string: {candidate: {scores..., overall, verdict}}
  judge_top_score     — float: overall score of the recommended name
  judge_flags         — comma-separated candidates that were flagged/rejected
  judge_status        — "ok" | "all_flagged" | "skipped" | "error"
"""
from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import BaseModel

from . import prompts
from .llm import structured_call

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-2.5-flash")


class CandidateJudgement(BaseModel):
    name: str
    buzzword_authenticity: int   # 1-5
    shopper_legibility: int      # 1-5
    click_appeal: int            # 1-5
    non_generic: int             # 1-5
    india_relevance: int         # 1-5
    overall_score: float         # mean of 5 criteria
    verdict: Literal["approve", "flag", "reject"]
    reason: str


def _judge_trend(trend: dict) -> list[CandidateJudgement]:
    """Run judge on one trend's candidate names. Returns list of judgements."""
    candidates = trend.get("candidate_names", [])
    if not candidates:
        return []

    candidates_list = "\n".join(f"{i+1}. {c}" for i, c in enumerate(candidates))
    prompt = prompts.fmt(
        "judge.evaluate",
        display_name=trend.get("display_name", trend.get("trend_name", "")),
        trend_category=trend.get("trend_category", ""),
        raw_signal=trend.get("raw_signal", ""),
        description=trend.get("description", ""),
        candidates_list=candidates_list,
    )
    try:
        result = structured_call(
            prompt,
            list[CandidateJudgement],
            system=prompts.get("judge.system"),
            name=f"judge_{trend.get('trend_id', 'unknown')}",
            temperature=0.1,
        )
        return result or []
    except Exception as e:
        print(f"  [judge] error on '{trend.get('display_name','')}': {e}")
        return []


def _patch_model(original_model: str) -> str:
    """Temporarily swap DEFAULT_MODEL in llm module to JUDGE_MODEL."""
    import src.agents.llm as llm_mod
    prev = llm_mod.DEFAULT_MODEL
    llm_mod.DEFAULT_MODEL = JUDGE_MODEL
    return prev


def _restore_model(prev: str) -> None:
    import src.agents.llm as llm_mod
    llm_mod.DEFAULT_MODEL = prev


def evaluate_trends(trends: list[dict]) -> list[dict]:
    """Add judge fields to each trend. Returns the same list, enriched.

    Swaps to JUDGE_MODEL for the duration of evaluation, then restores
    the original model so Agent 3 / other callers are unaffected.
    """
    prev_model = _patch_model(JUDGE_MODEL)
    print(f"[judge] evaluating {len(trends)} trends with model={JUDGE_MODEL}")

    approved = flagged = rejected = errors = 0

    try:
        for t in trends:
            judgements = _judge_trend(t)
            if not judgements:
                t["judge_recommended"] = t.get("display_name", "")
                t["judge_scores"] = "{}"
                t["judge_top_score"] = 0.0
                t["judge_flags"] = ""
                t["judge_status"] = "error"
                errors += 1
                continue

            # Sort by overall_score descending; pick best approved, else best overall
            judgements.sort(key=lambda j: j.overall_score, reverse=True)
            approved_j = [j for j in judgements if j.verdict == "approve"]
            best = approved_j[0] if approved_j else judgements[0]

            scores_dict = {
                j.name: {
                    "buzzword_authenticity": j.buzzword_authenticity,
                    "shopper_legibility": j.shopper_legibility,
                    "click_appeal": j.click_appeal,
                    "non_generic": j.non_generic,
                    "india_relevance": j.india_relevance,
                    "overall": round(j.overall_score, 2),
                    "verdict": j.verdict,
                    "reason": j.reason,
                }
                for j in judgements
            }

            flag_names = [j.name for j in judgements if j.verdict in ("flag", "reject")]
            all_bad = all(j.verdict != "approve" for j in judgements)

            t["judge_recommended"] = best.name
            t["judge_scores"] = json.dumps(scores_dict, ensure_ascii=False)
            t["judge_top_score"] = round(best.overall_score, 2)
            t["judge_flags"] = ", ".join(flag_names)
            t["judge_status"] = "all_flagged" if all_bad else "ok"

            # Verdict tally
            for j in judgements:
                if j.verdict == "approve":
                    approved += 1
                elif j.verdict == "flag":
                    flagged += 1
                else:
                    rejected += 1

    finally:
        _restore_model(prev_model)

    total_candidates = approved + flagged + rejected
    print(f"[judge] done — {total_candidates} candidates: "
          f"{approved} approved / {flagged} flagged / {rejected} rejected / {errors} errors")
    all_flagged_trends = sum(1 for t in trends if t.get("judge_status") == "all_flagged")
    if all_flagged_trends:
        print(f"[judge] {all_flagged_trends} trends have NO approved candidates — review needed")

    return trends
