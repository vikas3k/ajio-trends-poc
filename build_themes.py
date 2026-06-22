"""Stage 1 (deterministic): clean the Impetus export, keep the trending trends
(by Impetus's own labels), and group them into themes.

Usage:
    .venv/bin/python build_themes.py

Reads input_data/Trend_Forecast_Full_May_2026(in).csv, writes:
    output/themes.csv          one row per theme (trending clusters only)
    output/normalized_rows.csv all raw rows with clean n_*/family columns
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))
from trends.cluster import build_themes, is_trending  # noqa: E402
from trends.normalize import normalize  # noqa: E402

INPUT = Path("input_data/Trend_Forecast_Full_May_2026(in).csv")
OUT_DIR = Path("output")


def main() -> None:
    raw = pd.read_csv(INPUT, encoding="utf-8", dtype=str).fillna("")
    print(f"Loaded {len(raw):,} raw trend rows.")

    norm = normalize(raw)
    OUT_DIR.mkdir(exist_ok=True)
    norm.to_csv(OUT_DIR / "normalized_rows.csv", index=False)

    trending = norm[is_trending(norm)].copy()
    print(f"Impetus flags {len(trending):,} of {len(raw):,} rows as trending "
          f"(Breakout Star / Consistently Rising / Rising momentum).")

    themes = build_themes(trending)
    covered = themes["n_trends"].sum()
    themes.to_csv(OUT_DIR / "themes.csv", index=False)

    print(f"Grouped them into {len(themes)} trending themes "
          f"covering {covered:,} of those rows.\n")
    cols = ["theme_id", "n_gender", "subcat_family", "style_family",
            "color_family", "top_patterns", "n_trends",
            "n_consistently_rising", "n_breakout_star", "n_rising_momentum"]
    with pd.option_context("display.max_rows", None, "display.width", 220,
                           "display.max_colwidth", 20):
        print(themes[cols].to_string(index=False))


if __name__ == "__main__":
    main()
