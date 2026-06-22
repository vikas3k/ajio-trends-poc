"""Stage 2 (creative): turn the trending attribute-clusters into real trend names.

Stage 1 groups the trending rows (per Impetus's own labels) into themes, each
with a clean attribute signature plus the raw Impetus signal counts. This stage
hands those themes to Gemini in a single structured-output call and gets back,
per theme:

    trend_name  - merchandising-ready name a buyer would recognise
    hook        - short catchy/editorial label
    rationale   - one line on why it's trending (grounded in the Impetus signal)

A single call (not one-per-theme) lets the model see all themes together so
names stay distinct and consistently styled. No invented scores are sent — only
Impetus's own attributes and trending labels.

Auth: Vertex AI (GOOGLE_GENAI_USE_VERTEXAI + project + ADC) or GEMINI_API_KEY.
Model: override with GEMINI_MODEL env var; defaults to gemini-2.5-pro.
"""
from __future__ import annotations

import json
import os
import time

import pandas as pd
from google import genai
from google.genai import types
from pydantic import BaseModel

DEFAULT_MODEL = "gemini-2.5-pro"

SYSTEM = """You are a fashion trend editor and social-media strategist for Reliance \
AJIO, a major Indian online fashion retailer. You coin TREND NAMES in the \
language of fashion TikTok, Instagram, and magazine trend reports - the kind of \
catchy, viral-feeling labels that name a *vibe* or *movement*, not a product. \
Think in the style of real trends like #QuietLuxury, #CoastalCowgirl, #BlokeCore, \
#MochaMousse, #CleanGirl, #OldMoney, #Balletcore, #IndieSleaze, #Cottagecore. \
Your names are evocative and shareable, yet still recognisably about the cluster's \
actual look - never a dry attribute list, never invented detail that isn't there."""

INSTRUCTIONS = """Below are {n} fashion micro-trend clusters for the Indian market. \
Each is an aggregate of similar product trends the forecasting model flagged as \
TRENDING, with its dominant attributes and the raw trending signal (how many \
items are 'Consistently Rising', 'Breakout Star', or have 'Rising' momentum, plus \
likely peak months).

For EACH cluster, coin a social/editorial trend identity and return:
- "theme_id": echo the cluster's id (integer) so I can join back.
- "hashtag": ONE punchy social-media hashtag naming the trend as a vibe/movement. \
Start with '#', use PascalCase, 1-3 words joined. Lean on real trend-naming \
conventions where they fit - the "-core" / "-aesthetic" / "-era" suffixes, \
season/mood framing, colour-as-mood. e.g. "#BrokenInBlues", "#UtilityCore", \
"#IndigoHour", "#SlipDressSummer", "#DesiResort", "#CargoComeback", "#QuietLinen". \
Make each one DISTINCT and genuinely catchy.
- "editorial_headline": a short magazine-style headline (3-6 words, Title Case) \
that could top a trend-report section. e.g. "The Broken-In Blue Edit", "Utility \
Goes Soft", "Slip Into Summer".
- "rationale": ONE sentence on why this trend is bubbling up now, grounded in \
the signal (rising momentum, breakout, peak months) and the look. No fabricated numbers.

Rules:
- Ground every name in the cluster's actual look (garment, colour, style, pattern) \
- evoke a vibe, but don't invent attributes that aren't there.
- Every hashtag must be DISTINCT - never reuse the same word across clusters.
- Indian-market-aware where the data supports it (festive, monsoon, resort, \
Indo-western, desi street style).
- Sound like a trend a person would actually post or a magazine would print.
- Return one object per cluster, covering all {n}.

Clusters:
{clusters}"""


class ThemeName(BaseModel):
    theme_id: int
    hashtag: str
    editorial_headline: str
    rationale: str


def _s(v) -> str:
    """Coerce possibly-NaN/None cell values to a clean string."""
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def _cluster_blurb(row: pd.Series) -> dict:
    """Compact, model-friendly description of one theme cluster."""
    return {
        "theme_id": int(row["theme_id"]),
        "gender": _s(row["n_gender"]),
        "garment_family": _s(row["subcat_family"]),
        "style": _s(row["style_family"]),
        "colour": _s(row["color_family"]),
        "specific_garments": _s(row["top_subcategories"]),
        "specific_colours": _s(row["top_colors"]),
        "patterns": _s(row["top_patterns"]),
        "fabrics": _s(row["top_fabrics"]),
        "lengths": _s(row["common_lengths"]),
        "n_trends": int(row["n_trends"]),
        "n_consistently_rising": int(row["n_consistently_rising"]),
        "n_breakout_star": int(row["n_breakout_star"]),
        "n_rising_momentum": int(row["n_rising_momentum"]),
        "dominant_alert": _s(row["dominant_alert"]),
        "peak_months": _s(row["peak_months"]),
        "example_products": _s(row["example_descriptions"]),
    }


def _name_batch(
    client, model: str, clusters: list[dict], retries: int = 4,
) -> dict[int, ThemeName]:
    """Name one batch of clusters; return {theme_id: ThemeName}.

    Retries transient network errors (token-refresh resets, etc.) with backoff.
    """
    prompt = INSTRUCTIONS.format(
        n=len(clusters), clusters=json.dumps(clusters, ensure_ascii=False, indent=1)
    )
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    response_mime_type="application/json",
                    response_schema=list[ThemeName],
                    temperature=0.6,
                ),
            )
            break
        except Exception as e:  # transient transport/refresh errors
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  batch retry {attempt}/{retries - 1} after error ({e}); "
                  f"waiting {wait}s ...")
            time.sleep(wait)

    if getattr(resp, "usage_metadata", None):
        u = resp.usage_metadata
        print(f"  batch of {len(clusters):>3}: {u.prompt_token_count} in / "
              f"{u.candidates_token_count} out tokens")
    return {item.theme_id: item for item in (resp.parsed or [])}


def name_themes(
    themes: pd.DataFrame, limit: int | None = None, batch_size: int = 20,
) -> pd.DataFrame:
    """Name themes with Gemini; return them with hashtag/headline/rationale cols.

    Naming is done in batches of `batch_size` so each hashtag stays grounded in
    its own cluster — a single 100+ item call drifts and mislabels the tail.
    `limit` is an optional plain head() cut (not a quality ranking; None = all).
    """
    work = (themes.head(limit) if limit else themes).copy()
    blurbs = [_cluster_blurb(r) for _, r in work.iterrows()]

    # Client picks up Vertex AI env vars (or GEMINI_API_KEY) from the environment.
    client = genai.Client()
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    named: dict[int, ThemeName] = {}
    for start in range(0, len(blurbs), batch_size):
        named.update(_name_batch(client, model, blurbs[start:start + batch_size]))

    work["hashtag"] = work["theme_id"].map(lambda i: getattr(named.get(i), "hashtag", ""))
    work["editorial_headline"] = work["theme_id"].map(lambda i: getattr(named.get(i), "editorial_headline", ""))
    work["rationale"] = work["theme_id"].map(lambda i: getattr(named.get(i), "rationale", ""))
    return work
