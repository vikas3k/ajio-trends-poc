"""Audit normalization maps against a new Impetus CSV export.

Run this whenever a new Impetus file arrives, BEFORE running the pipeline.
It tells you which Color / Style / Subcategory values are not in the maps
in normalize.py, suggests the closest family, and tells you what to add.

Usage:
    .venv/bin/python scripts/audit_mappings.py input_data/your_new_export.csv

Output:
    - Per column: unmapped values, fuzzy-suggested family, row count
    - Summary: total unmapped count across all columns
    - No files are changed — this is read-only
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make src importable from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import difflib

import pandas as pd

from trends.normalize import (
    _COLOR_MAP,
    _STYLE_MAP,
    _SUBCAT_LOWER,
    _clean,
    _fix_mojibake,
)

# ---------------------------------------------------------------------------
# Config: which columns to audit and which map to check against
# ---------------------------------------------------------------------------
CHECKS = [
    {
        "col":         "Color",
        "map":         {k: v[1] for k, v in _COLOR_MAP.items()},  # key -> family
        "label":       "COLOR",
        "note":        "Add to _COLOR_MAP as: \"raw\": (\"Display Name\", \"Family\")",
    },
    {
        "col":         "Style",
        "map":         {k: v[1] for k, v in _STYLE_MAP.items()},
        "label":       "STYLE",
        "note":        "Add to _STYLE_MAP as: \"raw\": (\"Display Name\", \"Family\")",
    },
    {
        "col":         "Subcategory",
        "map":         _SUBCAT_LOWER,                              # key -> family
        "label":       "SUBCATEGORY",
        "note":        "Add to _SUBCAT_MAP as: \"raw\": \"Family\"",
    },
]


def _suggest(value: str, families: list[str]) -> str:
    """Fuzzy-match value against known family names; return closest or '?'."""
    matches = difflib.get_close_matches(value, families, n=1, cutoff=0.4)
    return matches[0] if matches else "?"


def _audit_column(
    series: pd.Series,
    mapping: dict[str, str],
    label: str,
    note: str,
) -> int:
    """Print audit results for one column. Returns count of unmapped values."""
    # Count occurrences of each unique raw value (mojibake-fixed, cleaned, lowercased).
    counts: dict[str, int] = {}
    for raw in series:
        if not isinstance(raw, str):
            continue
        key = _clean(_fix_mojibake(raw)).strip().lower()
        if key:
            counts[key] = counts.get(key, 0) + 1

    unmapped = {k: v for k, v in counts.items() if k not in mapping}
    mapped_n = len(counts) - len(unmapped)

    print(f"\n{'=' * 60}")
    print(f"{label}  —  {mapped_n}/{len(counts)} unique values mapped")
    print(f"  {note}")
    print(f"{'=' * 60}")

    if not unmapped:
        print("  ✓ All values mapped — nothing to do.")
        return 0

    known_families = sorted(set(mapping.values()))
    # Sort by row count descending so high-volume gaps appear first.
    rows = sorted(unmapped.items(), key=lambda x: -x[1])

    print(f"  {'RAW VALUE':<30} {'ROWS':>6}   SUGGESTED FAMILY")
    print(f"  {'-'*30} {'-'*6}   {'-'*25}")
    for raw, n in rows:
        suggestion = _suggest(raw, known_families)
        flag = "  ← HIGH VOLUME" if n >= 100 else ""
        print(f"  {raw:<30} {n:>6}   {suggestion}{flag}")

    return len(unmapped)


def main(csv_path: str) -> None:
    path = Path(csv_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    print(f"\nAudit: {path.name}  ({path.stat().st_size // 1024} KB)")
    df = pd.read_csv(path, dtype=str).fillna("")

    total_unmapped = 0
    for check in CHECKS:
        col = check["col"]
        if col not in df.columns:
            print(f"\n[SKIP] Column '{col}' not found in this export.")
            continue
        total_unmapped += _audit_column(
            df[col], check["map"], check["label"], check["note"]
        )

    print(f"\n{'=' * 60}")
    if total_unmapped == 0:
        print("✓ AUDIT PASSED — all values are mapped. Safe to run the pipeline.")
    else:
        print(f"✗ AUDIT FOUND {total_unmapped} unmapped value(s) across all columns.")
        print("  Review the suggestions above, update src/trends/normalize.py,")
        print("  then re-run this script to confirm before running the pipeline.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: .venv/bin/python scripts/audit_mappings.py <path_to_csv>")
        sys.exit(1)
    main(sys.argv[1])
