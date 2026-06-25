"""Export trends to a Google Sheets-friendly CSV for offline review.

Produces output/trends_for_review.csv with:
  - One row per trend
  - Candidate names split into separate columns (Candidate_1 … Candidate_5)
  - A pre-filled 'Approved_Name' column (empty for pending, current value otherwise)
  - A 'Review_Status' column with the current status
  - Instructions row at the top for reviewers

Run:
    .venv/bin/python export_for_sheets.py

After review, import the sheet back:
    .venv/bin/python import_from_sheets.py  output/trends_for_review.csv
"""
from __future__ import annotations

import os
import datetime
import pandas as pd

INPUT_CSV = os.path.join(os.path.dirname(__file__), "output", "agentic_trends.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "output", "trends_for_review.csv")
MAX_CANDIDATES = 5


def _split_candidates(raw: str) -> list[str]:
    return [c.strip() for c in str(raw).split("|") if c.strip()]


def main() -> None:
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")

    rows = []
    for _, r in df.iterrows():
        candidates = _split_candidates(r.get("candidate_names", ""))
        cand_cols = {f"Candidate_{i+1}": (candidates[i] if i < len(candidates) else "")
                     for i in range(MAX_CANDIDATES)}
        rows.append({
            "Trend_ID":         r["trend_id"],
            "Current_Name":     r["trend_name"],
            "Review_Status":    r.get("review_status", "pending"),
            "Approved_Name":    r.get("approved_name", ""),
            **cand_cols,
            "Category":         r.get("trend_category", ""),
            "Source":           r.get("source", ""),
            "Momentum":         r.get("momentum_label", ""),
            "Validity_Window":  r.get("validity_window", ""),
            "Description":      r.get("description", ""),
            "Raw_Signal":       r.get("raw_signal", ""),
            "Reviewer":         r.get("reviewer", ""),
        })

    out = pd.DataFrame(rows)

    # Instructions row so stakeholders know what to fill
    instr = {col: "" for col in out.columns}
    instr["Trend_ID"]      = "--- INSTRUCTIONS ---"
    instr["Current_Name"]  = "Do NOT edit columns to the right of Reviewer"
    instr["Review_Status"] = "Set to: approved / rejected / pending"
    instr["Approved_Name"] = "Copy one of Candidate_1..5 here, or type a custom name"
    out = pd.concat([pd.DataFrame([instr]), out], ignore_index=True)

    out.to_csv(OUTPUT_CSV, index=False)
    pending = (df.get("review_status", pd.Series(dtype=str)) == "pending").sum()
    print(f"Exported {len(df)} trends ({pending} pending) -> {OUTPUT_CSV}")
    print("Upload to Google Sheets, fill Approved_Name + Review_Status, then run import_from_sheets.py")


if __name__ == "__main__":
    main()
