"""Identify trending trends (using Impetus's own labels) and group them into
themes for naming.

No invented scoring. "Trending" is decided purely by the signal columns Impetus
already provides and defines:
    - Alert_Type == "Breakout Star" or "Consistently Rising"
    - Recent_Momentum > MOMENTUM_THRESHOLD  (numeric in this export)

A *theme* is a cluster of trending rows that share the same coarse signature:
    (Gender, Subcategory family, Style family, Colour family)

Themes are not ranked by any computed strength — they're just grouped and
described, with the raw Impetus signal counts shown so you can see *why* each
cluster qualified as trending.
"""
from __future__ import annotations

import pandas as pd

# Clustering signature: garment family + style + colour gives descriptive,
# trend-like clusters. Tune to make themes broader/narrower.
DEFAULT_KEYS = [
    "n_gender", "subcat_family", "style_family", "color_family",
]

# Impetus's own "this is emerging/trending" alerts.
_TRENDING_ALERTS = {"breakout star", "consistently rising"}

# Recent_Momentum is numeric in this export (Score_Change_1Mo / Current_Score).
# Values <= this are noise (zero, rounding, or very slow drift).
# Top ~31% of rows are above 0.01 — a meaningful acceleration signal.
MOMENTUM_THRESHOLD = 0.01


def is_trending(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: rows Impetus itself flags as trending/emerging."""
    alert = df["Alert_Type"].str.strip().str.lower()
    alert_flag = alert.isin(_TRENDING_ALERTS)

    # Handle both numeric exports and legacy text exports ("Rising").
    mom_raw = df["Recent_Momentum"].str.strip()
    mom_numeric = pd.to_numeric(mom_raw, errors="coerce")
    if mom_numeric.notna().mean() > 0.5:
        # Numeric export: use threshold
        momentum_flag = mom_numeric > MOMENTUM_THRESHOLD
    else:
        # Legacy text export: match "Rising" label
        momentum_flag = mom_raw.str.lower().eq("rising")

    return alert_flag | momentum_flag


def _count(s: pd.Series, *values: str) -> int:
    want = {v.lower() for v in values}
    return int(s.str.strip().str.lower().isin(want).sum())


def _mode(s: pd.Series) -> str:
    s = s[s.astype(bool)]
    return s.mode().iat[0] if len(s) else ""


def _top_values(s: pd.Series, n: int = 4) -> list[str]:
    s = s[s.astype(bool)]
    return list(s.value_counts().head(n).index)


def build_themes(
    df: pd.DataFrame,
    keys: list[str] | None = None,
    min_size: int = 2,
) -> pd.DataFrame:
    """Cluster the (already trending) rows into themes; one row per theme.

    Themes are described, not scored. Clusters smaller than `min_size` are
    dropped (too thin to call a theme). Output is ordered by cluster size only
    (a transparent count, not a ranking signal).
    """
    keys = keys or DEFAULT_KEYS
    records = []

    for key_vals, g in df.groupby(keys, dropna=False):
        if len(g) < min_size:
            continue
        key_vals = key_vals if isinstance(key_vals, tuple) else (key_vals,)
        meta = dict(zip(keys, key_vals))

        records.append({
            **meta,
            "n_trends": len(g),
            # Transparent Impetus signal counts — the "why it's trending".
            "n_consistently_rising": _count(g["Alert_Type"], "Consistently Rising"),
            "n_breakout_star": _count(g["Alert_Type"], "Breakout Star"),
            "n_rising_momentum": _count(g["Recent_Momentum"], "Rising"),
            "n_top_performer": _count(g["Top_Performer_Today"], "Yes"),
            "n_breakout_high": _count(g["Breakout_Likelihood"], "High"),
            "dominant_alert": _mode(g["Alert_Type"]),
            "top_subcategories": ", ".join(_top_values(g["n_subcategory"])),
            "top_colors": ", ".join(_top_values(g["n_color"])),
            "top_styles": ", ".join(_top_values(g["n_style"])),
            "top_patterns": ", ".join(_top_values(g["n_pattern"])),
            "top_fabrics": ", ".join(_top_values(g["n_fabric"], 3)),
            "common_lengths": ", ".join(_top_values(g["n_length"], 3)),
            "peak_months": ", ".join(_top_values(g["Peak_Month"], 3)),
            # A few example raw descriptions, for the namer to ground on.
            "example_descriptions": " | ".join(
                g["Trend_Description"].head(6).tolist()
            ),
            "trend_ids": ", ".join(g["Trend_ID"].head(50).tolist()),
        })

    themes = pd.DataFrame(records).sort_values(
        "n_trends", ascending=False
    ).reset_index(drop=True)
    themes.insert(0, "theme_id", themes.index + 1)
    return themes
