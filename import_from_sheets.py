"""Import reviewed Google Sheet back into agentic_trends.csv.

Usage:
    .venv/bin/python import_from_sheets.py output/trends_for_review.csv

Updates review_status, approved_name, and reviewer in agentic_trends.csv
for any row where Review_Status is 'approved' or 'rejected'.
Skips the instructions row and rows still marked 'pending'.
"""
from __future__ import annotations

import os
import sys
import datetime
import pandas as pd

TRENDS_CSV = os.path.join(os.path.dirname(__file__), "output", "agentic_trends.csv")


def main(review_csv: str) -> None:
    reviews = pd.read_csv(review_csv, dtype=str).fillna("")
    # Drop the instructions row
    reviews = reviews[reviews["Trend_ID"] != "--- INSTRUCTIONS ---"]
    # Only apply rows that have been acted on
    reviews = reviews[reviews["Review_Status"].isin(["approved", "rejected"])]

    if reviews.empty:
        print("No approved/rejected rows found — nothing to import.")
        return

    trends = pd.read_csv(TRENDS_CSV, dtype=str).fillna("")
    updated = 0
    for _, r in reviews.iterrows():
        mask = trends["trend_id"] == r["Trend_ID"]
        if not mask.any():
            print(f"  [warn] Trend_ID {r['Trend_ID']} not found in agentic_trends.csv — skipped")
            continue
        trends.loc[mask, "review_status"] = r["Review_Status"]
        trends.loc[mask, "approved_name"] = r["Approved_Name"] if r["Review_Status"] == "approved" else ""
        trends.loc[mask, "reviewer"] = r.get("Reviewer", "")
        if "reviewed_at" not in trends.columns:
            trends["reviewed_at"] = ""
        trends.loc[mask, "reviewed_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        updated += 1

    trends.to_csv(TRENDS_CSV, index=False)
    print(f"Imported {updated} review(s) into {TRENDS_CSV}")
    counts = trends["review_status"].value_counts().to_dict()
    print(f"Status breakdown: {counts}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python import_from_sheets.py <path_to_review_csv>")
        sys.exit(1)
    main(sys.argv[1])
