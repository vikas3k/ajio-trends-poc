"""Generation-side post-processing for the trend catalogue (no mapping, no graph
changes). Adds the metadata the PRD asks for on the generation side:

  - transparent momentum  (from Impetus's own labels - explainable, not a score)
  - validity_window       (rule-based for attribute trends; LLM-set for others)
  - buzzword evidence      (recency / confidence pulled from the buzzword dict)
  - review fields          (review_status / approved_name / reviewer)
  - lifecycle + dedup      (new/rising/peak/fading across runs, persisted store)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path


# --- helpers ---------------------------------------------------------------
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _norm_cat(c: str) -> str:
    return (c or "").strip().lower()


def _trend_key(t: dict) -> str:
    """Stable identity for a trend across runs: category + name slug."""
    return f"{_norm_cat(t.get('trend_category'))}:{_slug(t.get('display_name'))}"


def _trend_id(key: str) -> str:
    return "trd_" + hashlib.sha1(key.encode()).hexdigest()[:10]


# --- 1. momentum + validity + buzzword evidence + review -------------------
def _attribute_momentum(t: dict, combo_lookup: dict) -> tuple[str, str, float]:
    """Transparent momentum for an Impetus-backed trend, from its member combos.

    Returns (momentum_label, momentum_basis, velocity_score).
    velocity_score is the mean velocity across member combos (Score_Change_1Mo /
    Current_Score), so it reflects demand acceleration, not just current level.
    """
    cr = bs = rm = apparels = 0
    velocities = []
    for cid in t.get("member_combo_ids", []) or []:
        c = combo_lookup.get(cid, {})
        cr += c.get("n_consistently_rising", 0)
        bs += c.get("n_breakout_star", 0)
        rm += c.get("n_rising_momentum", 0)
        apparels += c.get("count", 0)
        v = c.get("velocity_score")
        if v is not None:
            velocities.append(v)
    if bs:
        label = "Breakout"
    elif cr >= max(2, rm):
        label = "Rising (consistent)"
    elif rm:
        label = "Rising"
    else:
        label = "Steady"
    basis = (f"{apparels} apparels; {bs} breakout-star, {cr} consistently-rising, "
             f"{rm} rising-momentum (Impetus labels)")
    velocity = round(sum(velocities) / len(velocities), 4) if velocities else 0.0
    return label, basis, velocity


def _rolling_window(today: _dt.date, weeks: int = 4) -> str:
    end = today + _dt.timedelta(weeks=weeks)
    return f"{today.isoformat()} to {end.isoformat()} (rolling {weeks}-week)"


# Impetus export is for May 2026; each trajectory step = one calendar month ahead.
_IMPETUS_EXPORT_MONTH = _dt.date(2026, 5, 1)


def _add_months(d: _dt.date, n: int) -> _dt.date:
    month = d.month + n
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return d.replace(year=year, month=month, day=1)


def _impetus_validity_window(combo_lookup: dict, member_combo_ids: list) -> str:
    """Derive validity window from Peak_Month and Trajectory_Summary of member combos.

    Start = first calendar month where trajectory turns 'Rise' across member combos.
    End   = latest Peak_Month across member combos + 2-week buffer.
    Falls back to None if data is missing, so caller can use rolling window.
    """
    rise_starts: list[_dt.date] = []
    peak_months: list[_dt.date] = []

    for cid in member_combo_ids or []:
        c = combo_lookup.get(cid, {})
        traj = c.get("trajectory_summary", "") or c.get("Trajectory_Summary", "")
        peak = c.get("peak_month", "") or c.get("Peak_Month", "")

        if traj:
            steps = traj.split("->")
            for i, step in enumerate(steps):
                if step.strip().lower() == "rise":
                    rise_starts.append(_add_months(_IMPETUS_EXPORT_MONTH, i + 1))
                    break

        if peak:
            try:
                peak_months.append(_dt.date.fromisoformat(peak + "-01" if len(peak) == 7 else peak))
            except ValueError:
                pass

    if not peak_months:
        return ""

    end = max(peak_months) + _dt.timedelta(weeks=2)
    start = min(rise_starts) if rise_starts else _dt.date.today()
    # If the derived window has already passed or start > end (conflicting signals),
    # return "" so the caller falls back to a rolling window from today.
    if end < _dt.date.today() or start > end:
        return ""
    source = f"Impetus: peak={max(peak_months).strftime('%b %Y')}"
    return f"{start.strftime('%b %Y')} to {end.strftime('%d %b %Y')} ({source})"


def enrich_trends(trends: list[dict], combo_lookup: dict, buzzwords: list[dict],
                  today: _dt.date | None = None) -> list[dict]:
    today = today or _dt.date.today()
    buzz_idx = {_slug(b.get("buzzword", "")): b for b in (buzzwords or [])}

    out = []
    for t in trends:
        t = dict(t)
        # momentum + velocity
        if t.get("member_combo_ids"):
            t["momentum_label"], t["momentum_basis"], t["velocity_score"] = _attribute_momentum(t, combo_lookup)
        else:
            t["momentum_label"], t["momentum_basis"] = "LLM/calendar", "context-generated (no catalogue signal)"
            t["velocity_score"] = 0.0

        # buzzword evidence (matched name, else display-name match)
        b = buzz_idx.get(_slug(t.get("matched_buzzword", ""))) or buzz_idx.get(_slug(t.get("display_name", "")))
        t["buzzword_recency"] = b.get("recency", "") if b else ""
        t["buzzword_confidence"] = b.get("confidence", "") if b else ("low" if t.get("source") == "llm" else "")
        t["buzzword_evidence"] = b.get("evidence", "") if b else ""

        # category_context: pick from the member combo with the best velocity rank
        # (lowest rank number = fastest accelerator). LLM trends get no context.
        if t.get("member_combo_ids"):
            best = min(
                (combo_lookup.get(cid, {}) for cid in t["member_combo_ids"]),
                key=lambda c: c.get("velocity_rank", 9999),
                default={},
            )
            t["category_context"] = best.get("category_context", "")
        else:
            t["category_context"] = ""

        # validity window: keep LLM-set windows; for attribute trends derive from
        # Impetus Peak_Month + Trajectory_Summary, fall back to rolling rule.
        if not t.get("validity_window"):
            if t.get("member_combo_ids"):
                impetus_window = _impetus_validity_window(combo_lookup, t["member_combo_ids"])
                t["validity_window"] = impetus_window or _rolling_window(today)
            else:
                t["validity_window"] = _rolling_window(today)

        # review fields (PRD section 4 / 8.7)
        t["review_status"] = "pending"
        t["approved_name"] = ""
        t["reviewer"] = ""
        out.append(t)
    return out


# --- 2. dedup within run + lifecycle across runs ---------------------------

# Thresholds for lifecycle stage transitions.
_RISING_MAX_RUNS = 3   # after this many runs, promote to "peak" even if still rising


def _stage(first_time: bool, momentum_label: str, runs_seen: int) -> str:
    """Four-state lifecycle: new -> rising -> peak -> fading (fading = missing runs).

    - new:    first time seen this trend
    - rising: seen before, momentum still active, within early run window
    - peak:   seen many times or momentum has plateaued
    - fading: assigned externally when misses > 0 (not from this function)
    """
    if first_time:
        return "new"
    if momentum_label in ("Breakout", "Rising", "Rising (consistent)") and runs_seen <= _RISING_MAX_RUNS:
        return "rising"
    return "peak"


def apply_lifecycle(trends: list[dict], store_path: Path,
                    today: _dt.date | None = None, expire_after_misses: int = 2) -> list[dict]:
    today = today or _dt.date.today()
    today_s = today.isoformat()

    # Within-run dedup: merge trends sharing the same identity key.
    merged: dict[str, dict] = {}
    for t in trends:
        k = _trend_key(t)
        if k in merged:
            m = merged[k]
            m["member_combo_ids"] = sorted(set(m.get("member_combo_ids", []) +
                                               t.get("member_combo_ids", [])))
            seen = set(m["candidate_names"])
            m["candidate_names"] += [c for c in t.get("candidate_names", []) if c not in seen]
        else:
            merged[k] = dict(t)

    # Load persisted store.
    store = {}
    if store_path.exists():
        try:
            store = json.loads(store_path.read_text())
        except Exception:
            store = {}

    out = []
    seen_keys = set()
    stage_counts: dict[str, int] = {}
    fading_names: list[str] = []

    for k, t in merged.items():
        seen_keys.add(k)
        prev = store.get(k)
        first_time = prev is None
        runs_seen = (prev["runs_seen"] + 1) if prev else 1
        first_seen = prev["first_seen"] if prev else today_s
        t["trend_id"] = _trend_id(k)
        t["lifecycle_stage"] = _stage(first_time, t.get("momentum_label", ""), runs_seen)
        t["first_seen"] = first_seen
        t["last_seen"] = today_s
        t["runs_seen"] = runs_seen
        stage_counts[t["lifecycle_stage"]] = stage_counts.get(t["lifecycle_stage"], 0) + 1
        store[k] = {
            "trend_id": t["trend_id"],
            "first_seen": first_seen,
            "last_seen": today_s,
            "runs_seen": runs_seen,
            "misses": 0,
            "display_name": t.get("display_name", ""),
            "trend_category": t.get("trend_category", ""),
            "momentum_label": t.get("momentum_label", ""),
            "velocity_score": t.get("velocity_score", 0.0),
        }
        out.append(t)

    # Age out store entries not seen this run.
    # Mark them fading (misses=1) before expiring at misses >= expire_after_misses.
    expired_names: list[str] = []
    for k, rec in list(store.items()):
        if k in seen_keys:
            continue
        rec["misses"] = rec.get("misses", 0) + 1
        if rec["misses"] >= expire_after_misses:
            expired_names.append(rec.get("display_name", k))
            del store[k]
        else:
            fading_names.append(rec.get("display_name", k))

    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(store, indent=1))

    # Run summary log so every execution shows what changed.
    total = len(out)
    print(f"\n[lifecycle] run summary — {today_s}")
    print(f"  this run : {total} trends  |  " +
          "  ".join(f"{s}={stage_counts.get(s,0)}" for s in ("new","rising","peak")))
    print(f"  store    : {len(store)} tracked entries")
    if fading_names:
        print(f"  fading   : {len(fading_names)} trends missing this run — "
              f"{', '.join(fading_names[:5])}" + (" ..." if len(fading_names) > 5 else ""))
    if expired_names:
        print(f"  expired  : {len(expired_names)} trends removed from store — "
              f"{', '.join(expired_names[:5])}" + (" ..." if len(expired_names) > 5 else ""))

    return out
