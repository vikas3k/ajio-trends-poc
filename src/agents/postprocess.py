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


# --- 1b. guardrails --------------------------------------------------------

def dedup_trend_names(trends: list[dict]) -> list[dict]:
    """Remove duplicate trend names produced by parallel batches.

    Keeps the copy with more member_combo_ids (richer signal). Logs every
    merge so the loss is visible in the run log.
    """
    seen: dict[str, dict] = {}
    for t in trends:
        key = _slug(t.get("display_name", ""))
        if not key:
            continue
        if key not in seen:
            seen[key] = t
        else:
            existing = seen[key]
            existing_n = len(existing.get("member_combo_ids") or [])
            current_n  = len(t.get("member_combo_ids") or [])
            if current_n > existing_n:
                print(f"[guardrail] dedup: keeping richer copy of '{t.get('display_name','')}' "
                      f"({current_n} combos vs {existing_n})")
                seen[key] = t
            else:
                print(f"[guardrail] dedup: dropping duplicate '{t.get('display_name','')}' "
                      f"({current_n} combos, keeping {existing_n}-combo copy)")

    result = list(seen.values())
    dropped = len(trends) - len(result)
    if dropped:
        print(f"[guardrail] dedup: removed {dropped} duplicate trend name(s), "
              f"{len(result)} unique trends remain")
    else:
        print(f"[guardrail] dedup: no duplicate names found ({len(result)} trends)")
    return result


JUDGE_SCORE_FLOOR = 2.5   # trends below this score get flagged for review


def apply_judge_floor(trends: list[dict]) -> list[dict]:
    """Flag trends whose best judge score is below JUDGE_SCORE_FLOOR.

    Sets review_status = 'needs_review' so they surface in the review app
    without being silently dropped. Trends with no judge data are left as-is.
    """
    flagged = 0
    for t in trends:
        score = t.get("judge_top_score")
        if score is None or score == "":
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if score < JUDGE_SCORE_FLOOR:
            t["review_status"] = "needs_review"
            flagged += 1

    print(f"[guardrail] judge floor ({JUDGE_SCORE_FLOOR}): "
          f"{flagged} trend(s) marked needs_review")
    return trends


def check_buzzword_coverage(trends: list[dict], buzzwords: list[dict]) -> None:
    """Log buzzword coverage: which buzzwords were used, which were missed.

    A buzzword is "used" if it appears in any trend's display_name, candidate_names,
    or matched_buzzword. Unused buzzwords are potential missed trend signals.
    """
    if not buzzwords:
        return

    # Build a set of all name tokens across all trends (lowercased slugs).
    used_tokens: set[str] = set()
    for t in trends:
        for name in [t.get("display_name", ""), t.get("matched_buzzword", "")] \
                    + (t.get("candidate_names") or []):
            used_tokens.add(_slug(name))

    used: list[str] = []
    unused: list[str] = []
    for b in buzzwords:
        bw = b.get("buzzword", "")
        if _slug(bw) in used_tokens:
            used.append(bw)
        else:
            unused.append(bw)

    pct = int(100 * len(used) / len(buzzwords)) if buzzwords else 0
    print(f"\n[guardrail] buzzword coverage: {len(used)}/{len(buzzwords)} buzzwords "
          f"used in trend names ({pct}%)")
    if used:
        print(f"  used    : {', '.join(used)}")
    if unused:
        print(f"  UNUSED  : {', '.join(unused)}")
        print(f"  ^ these buzzwords had no matching trend — consider adding them to prompts "
              f"or they may indicate missing trend coverage")


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


# --- 3. ranking ------------------------------------------------------------

# Weights for the composite ranking score.
# Signals with no data for a trend (e.g. LLM-sourced trends have no
# bucket_rank_score) are replaced with 0 so they don't block ranking —
# they just score lower on that dimension.
_RANK_WEIGHTS = {
    "velocity_score":    0.40,  # demand acceleration — strongest forward signal
    "bucket_rank_score": 0.30,  # Impetus forecast strength (predicted score, 4mo, confidence)
    "momentum_boost":    0.15,  # Impetus alert type — Breakout > Rising > Steady
    "lifecycle_boost":   0.10,  # new/rising trends get a small boost over peak
    "time_decay":        0.05,  # trends closer to peak date rank higher right now
}

_LIFECYCLE_BOOST = {
    "new":    1.0,
    "rising": 0.8,
    "peak":   0.4,
    "fading": 0.0,
}

_MOMENTUM_BOOST = {
    "Breakout":             1.0,
    "Rising (consistent)":  0.8,
    "Rising":               0.6,
    "Steady":               0.3,
    "LLM/calendar":         0.0,  # no Impetus signal
}


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val not in (None, "", "nan") else default
    except (TypeError, ValueError):
        return default


def _minmax_normalise(values: list[float]) -> list[float]:
    import math
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def rank_trends(trends: list[dict]) -> list[dict]:
    """Add global_rank and category_rank to every trend.

    Global rank  : all trends sorted by composite score.
    Category rank: ranked within each trend_category group.

    Composite score (0–1):
      40% velocity_score     — demand acceleration from Impetus
      30% judge_top_score    — name quality (0–5 normalised to 0–1)
      20% bucket_rank_score  — Impetus forecast strength (already 0–1)
      10% lifecycle_boost    — new > rising > peak > fading

    LLM-sourced trends (occasion/festival/event/functional) have no Impetus
    signal so velocity and bucket_rank_score default to 0. They rank on
    judge score and lifecycle only, and sit in their own category_rank group.
    """
    if not trends:
        return trends

    import datetime

    velocities    = [_safe_float(t.get("velocity_score")) for t in trends]
    bucket_scores = [_safe_float(t.get("bucket_rank_score")) for t in trends]
    lifecycle     = [_LIFECYCLE_BOOST.get(t.get("lifecycle_stage", ""), 0.0) for t in trends]
    momentum      = [_MOMENTUM_BOOST.get(t.get("momentum_label", ""), 0.0) for t in trends]

    # Time decay: how close is the trend's peak to today?
    # Trends peaking sooner score higher. LLM trends with no peak get 0.
    today = datetime.date.today()
    def _peak_proximity(t: dict) -> float:
        vw = t.get("validity_window", "")
        # Try to extract a date from validity_window or peak_month
        peak = t.get("peak_month", "") or ""
        for candidate in [peak, vw]:
            if not candidate:
                continue
            # Match YYYY-MM or YYYY-MM-DD
            import re as _re
            m = _re.search(r"(\d{4}-\d{2})(?:-\d{2})?", str(candidate))
            if m:
                try:
                    peak_date = _dt.date.fromisoformat(m.group(1) + "-01")
                    days_away = (peak_date - today).days
                    if days_away < 0:
                        return 0.0   # already past peak
                    # Score: 1.0 if peaking within 30 days, decays to 0 at 180 days+
                    return max(0.0, 1.0 - days_away / 180.0)
                except ValueError:
                    continue
        return 0.0

    time_decay = [_peak_proximity(t) for t in trends]

    vel_n      = _minmax_normalise(velocities)
    bucket_n   = _minmax_normalise(bucket_scores)
    life_n     = _minmax_normalise(lifecycle)
    momentum_n = _minmax_normalise(momentum)
    decay_n    = _minmax_normalise(time_decay)

    for i, t in enumerate(trends):
        t["_composite"] = round(
            _RANK_WEIGHTS["velocity_score"]    * vel_n[i] +
            _RANK_WEIGHTS["bucket_rank_score"] * bucket_n[i] +
            _RANK_WEIGHTS["momentum_boost"]    * momentum_n[i] +
            _RANK_WEIGHTS["lifecycle_boost"]   * life_n[i] +
            _RANK_WEIGHTS["time_decay"]        * decay_n[i],
            4,
        )
        t["rank_score"] = t["_composite"]
        t["rank_basis"] = (
            f"velocity={velocities[i]:.4f}(w=0.40) | "
            f"bucket={bucket_scores[i]:.4f}(w=0.30) | "
            f"momentum={t.get('momentum_label','')}(w=0.15) | "
            f"lifecycle={t.get('lifecycle_stage','')}(w=0.10) | "
            f"time_decay={time_decay[i]:.3f}(w=0.05)"
        )

    # Global rank.
    trends.sort(key=lambda t: t["_composite"], reverse=True)
    for rank, t in enumerate(trends, 1):
        t["global_rank"] = rank

    # Category rank.
    from collections import defaultdict
    cat_groups: dict[str, list] = defaultdict(list)
    for t in trends:
        cat_groups[t.get("trend_category", "unknown")].append(t)

    for cat, group in cat_groups.items():
        group.sort(key=lambda t: t["_composite"], reverse=True)
        for rank, t in enumerate(group, 1):
            t["category_rank"] = rank

    for t in trends:
        t.pop("_composite", None)

    print(f"\n[ranking] {len(trends)} trends ranked — weights: velocity=40% | bucket=30% | momentum=15% | lifecycle=10% | time_decay=5%")
    for cat, group in sorted(cat_groups.items()):
        top = group[0]
        print(f"  {cat:<22} {len(group):>3} trends | "
              f"#1 → '{top.get('display_name', '')}' (score={top.get('rank_score', 0):.4f})")

    return trends
