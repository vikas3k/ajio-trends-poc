"""Shared state passed between the three agents in the LangGraph graph."""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # --- input ---
    input_path: str
    trending_only: bool

    # --- Agent 1: attribute selection + cleaning ---
    schema_preview: str            # column names + a few sample values (LLM input)
    attribute_columns: list[str]   # columns the agent judged to be apparel attributes
    column_reasoning: str          # why those columns
    cleaned_records: list[dict]    # distinct cleaned attribute combos (+ counts, ids)

    # --- Agent 2: generation + naming (multi-source per PRD section 6) ---
    trend_brief: str               # grounded social/market research text (6.2/6.3)
    buzzwords: list[dict]          # buzzword dictionary (6.3): name, maps_to, category
    trends: list[dict]             # generated trends from all sources, pre-classification
                                   #   each: candidate_names, display_name, description,
                                   #   rationale, raw_signal, source, [member_combo_ids],
                                   #   [provisional_category], [validity_window]

    # --- Agent 3: classification into the PRD 4-category taxonomy ---
    classified_trends: list[dict]  # trends + {trend_category, category_reason}

    # --- misc ---
    notes: dict[str, Any]
