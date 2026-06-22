"""End-to-end: clean -> keep trending (Impetus labels) -> cluster -> name with Gemini.

Usage:
    # Vertex AI (this project):
    export GOOGLE_APPLICATION_CREDENTIALS=.gcp/adc.json
    export GOOGLE_GENAI_USE_VERTEXAI=true
    export GOOGLE_CLOUD_PROJECT=sr-proj-ecom-nonprod-ajioall
    export GOOGLE_CLOUD_LOCATION=us-central1
    .venv/bin/python run_pipeline.py [LIMIT]

LIMIT optionally caps how many themes to name (a plain size-ordered head cut,
not a quality ranking). Omit to name all trending themes.

Writes output/named_themes.csv (the deliverable) and the Stage-1 artifacts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))
from trends.cluster import build_themes, is_trending  # noqa: E402
from trends.name_themes import name_themes  # noqa: E402
from trends.normalize import normalize  # noqa: E402

INPUT = Path("input_data/Trend_Forecast_Full_May_2026(in).csv")
OUT_DIR = Path("output")


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    have_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    have_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
    if not (have_api_key or have_vertex):
        sys.exit("ERROR: configure Gemini auth before the naming step — either\n"
                 "       GEMINI_API_KEY=... (Developer API), or Vertex AI via\n"
                 "       GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT + "
                 "GOOGLE_APPLICATION_CREDENTIALS.\n"
                 "       (Stage 1 alone runs key-free via build_themes.py.)")

    raw = pd.read_csv(INPUT, encoding="utf-8", dtype=str).fillna("")
    print(f"Loaded {len(raw):,} raw rows -> normalizing ...")
    norm = normalize(raw)
    trending = norm[is_trending(norm)].copy()
    print(f"{len(trending):,} flagged trending by Impetus -> clustering ...")
    themes = build_themes(trending)
    OUT_DIR.mkdir(exist_ok=True)
    themes.to_csv(OUT_DIR / "themes.csv", index=False)

    n_to_name = limit if limit else len(themes)
    print(f"Naming {n_to_name} of {len(themes)} trending themes with Gemini ...")
    named = name_themes(themes, limit=limit)

    deliverable = named[[
        "theme_id", "hashtag", "editorial_headline", "rationale",
        "n_gender", "subcat_family", "color_family", "style_family",
        "top_patterns", "n_trends", "n_consistently_rising", "n_breakout_star",
        "n_rising_momentum", "dominant_alert", "peak_months", "trend_ids",
    ]]
    deliverable.to_csv(OUT_DIR / "named_themes.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'named_themes.csv'} ({len(deliverable)} named themes).\n")

    with pd.option_context("display.max_rows", None, "display.width", 220,
                           "display.max_colwidth", 44):
        print(named[["theme_id", "hashtag", "editorial_headline", "rationale"]].to_string(index=False))


if __name__ == "__main__":
    main()
