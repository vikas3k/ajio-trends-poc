"""Run the 3-agent LangGraph trend-naming system on the Impetus export.

Auth / config (env vars):
    # Gemini via Vertex AI:
    GOOGLE_APPLICATION_CREDENTIALS=.gcp/adc.json
    GOOGLE_GENAI_USE_VERTEXAI=true
    GOOGLE_CLOUD_PROJECT=sr-proj-ecom-nonprod-ajioall
    GOOGLE_CLOUD_LOCATION=us-central1
    # Langfuse tracing (optional; degrades to no-op if unset):
    LANGFUSE_PUBLIC_KEY=...  LANGFUSE_SECRET_KEY=...  LANGFUSE_HOST=...

Usage:
    .venv/bin/python run_agents.py [--all]      # --all = use every row, not just trending

Writes output/agentic_trends.csv (trend + classification + member combos).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()  # pull Vertex + Langfuse config from .env before anything reads env

sys.path.insert(0, str(Path(__file__).parent / "src"))
from agents.graph import build_graph  # noqa: E402
from agents.observability import flush, langfuse_enabled  # noqa: E402
from agents.postprocess import apply_lifecycle, enrich_trends  # noqa: E402
from agents.gtrends import validate_trends  # noqa: E402
from agents.judge import evaluate_trends  # noqa: E402

INPUT = Path("input_data/trend-forecast-prod-21-june-brands (1).csv")
OUT_DIR = Path("output")


def main() -> None:
    trending_only = "--all" not in sys.argv[1:]
    print(f"Langfuse tracing: {'ON' if langfuse_enabled() else 'off (no keys)'}")
    print(f"Scope: {'trending rows only' if trending_only else 'all rows'}\n")

    graph = build_graph()
    final = graph.invoke({"input_path": str(INPUT), "trending_only": trending_only})
    flush()

    trends = final.get("classified_trends", [])
    combo_lookup = {r["combo_id"]: r for r in final.get("cleaned_records", [])}
    OUT_DIR.mkdir(exist_ok=True)

    # Generation-side post-processing: momentum + validity + buzzword evidence +
    # review fields, then cross-run dedup + lifecycle against a persisted store.
    trends = enrich_trends(trends, combo_lookup, final.get("buzzwords", []))
    trends = validate_trends(trends)
    trends = apply_lifecycle(trends, OUT_DIR / "trend_store.json")
    trends = evaluate_trends(trends)

    # PRD-shaped trend catalogue (one record per trend, with §5.2 metadata).
    rows = []
    for t in trends:
        member_ids = t.get("member_combo_ids", []) or []
        n_apparels = sum(combo_lookup.get(c, {}).get("count", 0) for c in member_ids)
        trend_ids = [
            tid for c in member_ids
            for tid in combo_lookup.get(c, {}).get("sample_trend_ids", [])
        ]
        label = t.get("momentum_label", "")
        basis = t.get("momentum_basis", "")
        velocity = t.get("velocity_score", 0.0) or 0.0
        momentum_summary = (
            f"{label} | velocity={velocity:.4f} | {basis}"
            if basis else label
        )
        rows.append({
            "trend_id": t.get("trend_id", ""),
            "trend_name": t["display_name"],
            "approved_name": t.get("approved_name", ""),
            "review_status": t.get("review_status", ""),
            "reviewer": t.get("reviewer", ""),
            "trend_category": t.get("trend_category", ""),
            "lifecycle_stage": t.get("lifecycle_stage", ""),
            "momentum_label": label,
            "momentum_basis": basis,
            "velocity_score": velocity,
            "momentum_summary": momentum_summary,
            "validity_window": t.get("validity_window", ""),
            "source": t.get("source", ""),
            "buzzword_confidence": t.get("buzzword_confidence", ""),
            "buzzword_recency": t.get("buzzword_recency", ""),
            "category_context": t.get("category_context", ""),
            "gtrends_score": t.get("gtrends_score", ""),
            "gtrends_momentum": t.get("gtrends_momentum", ""),
            "gtrends_term": t.get("gtrends_term", ""),
            "gtrends_status": t.get("gtrends_status", ""),
            "judge_recommended": t.get("judge_recommended", ""),
            "judge_top_score": t.get("judge_top_score", ""),
            "judge_flags": t.get("judge_flags", ""),
            "judge_status": t.get("judge_status", ""),
            "judge_scores": t.get("judge_scores", ""),
            "candidate_names": " | ".join(t.get("candidate_names", [])),
            "raw_signal": t.get("raw_signal", ""),
            "description": t.get("description", ""),
            "rationale": t.get("rationale", ""),
            "category_reason": t.get("category_reason", ""),
            "first_seen": t.get("first_seen", ""),
            "runs_seen": t.get("runs_seen", ""),
            "n_apparels": n_apparels,
            "member_combo_ids": ", ".join(map(str, member_ids)),
            "sample_trend_ids": ", ".join(trend_ids[:8]),
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "agentic_trends.csv", index=False)

    # Buzzword dictionary artifact (PRD §6.3).
    buzz = pd.DataFrame(final.get("buzzwords", []))
    if not buzz.empty:
        buzz.to_csv(OUT_DIR / "buzzword_dictionary.csv", index=False)

    print(f"\nWrote {OUT_DIR / 'agentic_trends.csv'} ({len(df)} trends), "
          f"{OUT_DIR / 'buzzword_dictionary.csv'} ({len(buzz)} buzzwords).\n")

    if not df.empty:
        order = ["occasion_festival", "event_driven", "functional", "attribute_driven"]
        df["_o"] = df["trend_category"].map({c: i for i, c in enumerate(order)}).fillna(9)
        with pd.option_context("display.max_rows", None, "display.width", 300,
                               "display.max_colwidth", 40):
            print(df.sort_values("_o")[["trend_name", "trend_category", "source",
                                        "momentum_label", "velocity_score",
                                        "gtrends_score", "gtrends_momentum",
                                        "judge_recommended", "judge_top_score",
                                        "judge_status", "lifecycle_stage",
                                        "review_status"]].to_string(index=False))


if __name__ == "__main__":
    main()
