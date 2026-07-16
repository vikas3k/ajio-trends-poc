"""Google Trends validation for named trends (India, Fashion context).

Queries Google Trends IN for each trend's display_name (and candidate names as
fallback) to validate that demand is still live today — not just what Impetus
captured in May 2026.

Usage:
    from agents.gtrends import validate_trends
    trends = validate_trends(trends)   # adds gtrends_score, gtrends_momentum, gtrends_term

Rate limiting strategy:
  1. Cross-run cache in trend_store.json — only NEW trends (never queried before)
     are sent to Google Trends. Returning trends reuse cached scores.
  2. Increased sleep (15s between batches) for the new-trends queries.
  3. If still rate-limited, marks affected trends as gtrends_status="rate_limited"
     and continues — the pipeline never blocks.

This reduces queries from ~145/run to ~10-20/run (only new trends each week).
"""
from __future__ import annotations

import json
import re
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")  # suppress urllib3 LibreSSL warning

_PYTRENDS_AVAILABLE = False
try:
    from pytrends.request import TrendReq as _TrendReq
    _PYTRENDS_AVAILABLE = True
except ImportError:
    pass

# India locale, IST (UTC+5:30 = 330 min)
_GEO = "IN"
_CAT = 0          # 185 = Fashion & Style, but returns empty too often; 0 = all categories
_TIMEFRAME = "today 3-m"
_BATCH_SIZE = 5   # pytrends max per call
_SLEEP_S = 15     # seconds between batches — increased from 6 to avoid rate limiting

# Cross-run gtrends cache lives alongside the lifecycle store.
_GTRENDS_CACHE_FILE = Path("output/gtrends_cache.json")

# Re-query cached results after this many days (trends can go stale).
_CACHE_TTL_DAYS = 7

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


def _load_cache() -> dict:
    """Load cross-run gtrends cache from disk."""
    if _GTRENDS_CACHE_FILE.exists():
        try:
            return json.loads(_GTRENDS_CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    """Persist gtrends cache to disk."""
    _GTRENDS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GTRENDS_CACHE_FILE.write_text(json.dumps(cache, indent=1))


def _cache_is_fresh(entry: dict) -> bool:
    """Return True if cached entry is within TTL."""
    import datetime
    queried = entry.get("queried_on", "")
    if not queried:
        return False
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(queried)).days
        return age < _CACHE_TTL_DAYS
    except ValueError:
        return False


def validate_trends(
    trends: list[dict],
    skip_sources: tuple[str, ...] = ("llm",),
) -> list[dict]:
    """Add gtrends_score, gtrends_momentum, gtrends_term, gtrends_status to each trend.

    Only queries Google Trends for trends not already in the cross-run cache
    (or whose cache entry is older than _CACHE_TTL_DAYS). This keeps queries
    to ~10-20/run instead of 145, avoiding rate limiting.
    """
    import datetime

    # Stamp defaults for all trends first.
    for t in trends:
        t.setdefault("gtrends_score", 0.0)
        t.setdefault("gtrends_momentum", "unavailable")
        t.setdefault("gtrends_term", "")
        t.setdefault("gtrends_status", "unavailable")

    if not _PYTRENDS_AVAILABLE:
        print("[gtrends] pytrends not installed — skipping validation")
        return trends

    # Load cross-run cache.
    disk_cache = _load_cache()
    today_s = datetime.date.today().isoformat()

    # Separate trends into: use cache vs need fresh query.
    to_query: list[dict] = []
    cache_hits = 0
    skipped = 0

    for t in trends:
        if t.get("source", "") in skip_sources:
            t["gtrends_momentum"] = "skipped"
            t["gtrends_status"] = "skipped (llm)"
            skipped += 1
            continue

        term = _best_term(t)
        t["gtrends_term"] = term

        cached = disk_cache.get(term)
        if cached and _cache_is_fresh(cached):
            # Restore from cache.
            t["gtrends_score"]    = cached["score"]
            t["gtrends_momentum"] = cached["momentum"]
            t["gtrends_status"]   = cached["status"]
            cache_hits += 1
        else:
            to_query.append(t)

    print(f"[gtrends] {cache_hits} from cache | {len(to_query)} to query | "
          f"{skipped} skipped (llm)")

    if not to_query:
        print("[gtrends] all trends served from cache — no API calls needed")
        return trends

    # Query only the uncached / stale trends.
    pt = _TrendReq(hl="en-IN", tz=330, timeout=(10, 25))
    unique_terms = list(dict.fromkeys(t["gtrends_term"] for t in to_query if t["gtrends_term"]))
    run_cache: dict[str, tuple[float, str]] = {}

    print(f"[gtrends] querying {len(unique_terms)} new terms (sleep={_SLEEP_S}s between batches) ...")
    for i in range(0, len(unique_terms), _BATCH_SIZE):
        batch = unique_terms[i: i + _BATCH_SIZE]
        results = _query_batch(pt, batch)
        run_cache.update(results)
        statuses = set(v[1] for v in results.values())
        print(f"  batch {i // _BATCH_SIZE + 1}: {batch} -> {statuses}")
        if i + _BATCH_SIZE < len(unique_terms):
            time.sleep(_SLEEP_S)

    # Attach results and update disk cache.
    for t in to_query:
        term = t["gtrends_term"]
        score, momentum = run_cache.get(term, (0.0, "no_data"))
        status = (
            "ok" if momentum not in ("no_data", "unavailable", "rate_limited", "niche")
            else momentum
        )
        t["gtrends_score"]    = score
        t["gtrends_momentum"] = momentum
        t["gtrends_status"]   = status

        # Only cache successful results — don't cache rate_limited/unavailable.
        if momentum not in ("rate_limited", "unavailable"):
            disk_cache[term] = {
                "score":      score,
                "momentum":   momentum,
                "status":     status,
                "queried_on": today_s,
            }

    _save_cache(disk_cache)

    # Summary
    ok      = sum(1 for t in trends if t.get("gtrends_status") == "ok")
    rising  = sum(1 for t in trends if t.get("gtrends_momentum") == "rising")
    falling = sum(1 for t in trends if t.get("gtrends_momentum") == "falling")
    niche   = sum(1 for t in trends if t.get("gtrends_momentum") == "niche")
    rl      = sum(1 for t in trends if t.get("gtrends_momentum") == "rate_limited")
    print(f"[gtrends] done: {ok} ok | {rising} rising | {falling} falling | "
          f"{niche} niche | {rl} rate_limited | cache size={len(disk_cache)}")

    return trends
