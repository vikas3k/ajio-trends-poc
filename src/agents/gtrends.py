"""Google Trends validation for named trends (India, Fashion context).

Queries Google Trends IN for each trend's display_name (and candidate names as
fallback) to validate that demand is still live today — not just what Impetus
captured in May 2026.

Usage:
    from agents.gtrends import validate_trends
    trends = validate_trends(trends)   # adds gtrends_score, gtrends_momentum, gtrends_term

Rate limiting: Google Trends allows ~1 request per 5s. This module batches up to
5 terms per call and sleeps between calls. If rate-limited, it marks affected
trends as gtrends_status="unavailable" and continues — the pipeline never blocks.

Caches within a run so the same term is never queried twice.
"""
from __future__ import annotations

import re
import time
import warnings
from typing import Optional

warnings.filterwarnings("ignore")  # suppress urllib3 LibreSSL warning

_PYTRENDS_AVAILABLE = False
try:
    from pytrends.request import TrendReq as _TrendReq
    _PYTRENDS_AVAILABLE = True
except ImportError:
    pass

# India locale, IST (UTC+5:30 = 330 min), Fashion & Style category
_GEO = "IN"
_CAT = 0          # 185 = Fashion & Style, but returns empty too often; 0 = all categories
_TIMEFRAME = "today 3-m"
_BATCH_SIZE = 5   # pytrends max per call
_SLEEP_S = 6      # seconds between batches (stay under rate limit)

# Thresholds for momentum classification
_RISE_THRESHOLD = 1.15   # recent avg > baseline * this -> rising
_FALL_THRESHOLD = 0.85   # recent avg < baseline * this -> falling
_MIN_SIGNAL = 5          # below this average score = niche/no-signal


def _clean_term(name: str) -> str:
    """Strip punctuation and shorten to a search-friendly query."""
    # Preserve possessives: "Men's" -> "Mens", not "Men s"
    t = re.sub(r"'s\b", "s", name)
    t = re.sub(r"[^\w\s]", " ", t).strip()
    return " ".join(t.split()[:5])  # max 5 words


def _momentum(series, term: str) -> tuple[float, str]:
    """Return (current_score, momentum_label) from a pytrends interest series."""
    vals = series[term].dropna()
    if vals.empty:
        return 0.0, "no_data"
    # Exclude partial (current) week
    try:
        import pandas as _pd
        partial_mask = series.get("isPartial", _pd.Series(False, index=series.index))
        vals = series.loc[~partial_mask.astype(bool), term].dropna()
    except Exception:
        pass
    if vals.empty:
        return 0.0, "no_data"

    recent_avg = float(vals.tail(4).mean())
    baseline_avg = float(vals.mean())

    if baseline_avg < _MIN_SIGNAL:
        momentum = "niche"
    elif recent_avg > baseline_avg * _RISE_THRESHOLD:
        momentum = "rising"
    elif recent_avg < baseline_avg * _FALL_THRESHOLD:
        momentum = "falling"
    else:
        momentum = "flat"

    return round(recent_avg, 1), momentum


def _query_batch(pt, terms: list[str]) -> dict[str, tuple[float, str]]:
    """Query one batch (≤5 terms). Returns {term: (score, momentum)}."""
    results = {}
    try:
        pt.build_payload(terms, timeframe=_TIMEFRAME, geo=_GEO, cat=_CAT)
        df = pt.interest_over_time()
        if df.empty:
            return {t: (0.0, "no_data") for t in terms}
        for term in terms:
            if term in df.columns:
                results[term] = _momentum(df, term)
            else:
                results[term] = (0.0, "no_data")
    except Exception as e:
        err = str(e)
        status = "rate_limited" if "429" in err else "unavailable"
        results = {t: (0.0, status) for t in terms}
    return results


def _best_term(trend: dict) -> str:
    """Pick the most search-friendly term for this trend.

    Prefers display_name. Falls back to a candidate if display_name is an
    editorial headline (>5 words or has a colon). Picks the candidate closest
    to 3 words — long enough to be specific, short enough to search well.
    """
    name = trend.get("display_name", "") or trend.get("trend_name", "")
    candidates = trend.get("candidate_names", [])
    words = name.split()
    if len(words) > 5 or ":" in name:
        if candidates:
            name = min(candidates, key=lambda c: abs(len(c.split()) - 3))
    return _clean_term(name)


def validate_trends(
    trends: list[dict],
    skip_sources: tuple[str, ...] = ("llm",),
) -> list[dict]:
    """Add gtrends_score, gtrends_momentum, gtrends_term, gtrends_status to each trend.

    LLM/calendar trends are skipped by default (no Impetus signal to validate).
    Trends from impetus/social_crawl get queried.

    Args:
        trends: list of trend dicts from Agent 2 / postprocess.
        skip_sources: sources to skip (default: llm only).
    """
    if not _PYTRENDS_AVAILABLE:
        print("[gtrends] pytrends not installed — skipping validation")
        for t in trends:
            t.setdefault("gtrends_score", 0.0)
            t.setdefault("gtrends_momentum", "unavailable")
            t.setdefault("gtrends_term", "")
            t.setdefault("gtrends_status", "unavailable")
        return trends

    pt = _TrendReq(hl="en-IN", tz=330, timeout=(10, 25))

    # Build term -> trend mapping; skip LLM sources
    term_map: dict[str, str] = {}   # term -> trend display_name (for lookup)
    skipped: set[str] = set()
    for t in trends:
        name = t.get("display_name", "") or t.get("trend_name", "")
        if t.get("source", "") in skip_sources:
            skipped.add(name)
            continue
        term = _best_term(t)
        if term:
            term_map[term] = name

    unique_terms = list(dict.fromkeys(term_map))  # deduplicated, order preserved
    cache: dict[str, tuple[float, str]] = {}

    print(f"[gtrends] querying {len(unique_terms)} terms "
          f"({len(skipped)} LLM trends skipped) ...")

    # Query in batches of _BATCH_SIZE
    for i in range(0, len(unique_terms), _BATCH_SIZE):
        batch = unique_terms[i: i + _BATCH_SIZE]
        results = _query_batch(pt, batch)
        cache.update(results)
        statuses = set(v[1] for v in results.values())
        print(f"  batch {i // _BATCH_SIZE + 1}: {batch} -> {statuses}")
        if i + _BATCH_SIZE < len(unique_terms):
            time.sleep(_SLEEP_S)

    # Attach results back to trends
    for t in trends:
        name = t.get("display_name", "") or t.get("trend_name", "")
        if name in skipped:
            t["gtrends_score"] = 0.0
            t["gtrends_momentum"] = "skipped"
            t["gtrends_term"] = ""
            t["gtrends_status"] = "skipped (llm)"
            continue

        term = _best_term(t)
        score, momentum = cache.get(term, (0.0, "no_data"))
        t["gtrends_score"] = score
        t["gtrends_momentum"] = momentum
        t["gtrends_term"] = term
        t["gtrends_status"] = (
            "ok" if momentum not in ("no_data", "unavailable", "rate_limited", "niche")
            else momentum
        )

    # Summary
    ok = sum(1 for t in trends if t.get("gtrends_status") == "ok")
    rising = sum(1 for t in trends if t.get("gtrends_momentum") == "rising")
    falling = sum(1 for t in trends if t.get("gtrends_momentum") == "falling")
    niche = sum(1 for t in trends if t.get("gtrends_momentum") == "niche")
    print(f"[gtrends] validation done: {ok} ok | {rising} rising | "
          f"{falling} falling | {niche} niche/low-signal")

    return trends
