"""Agent 1 - Attribute Selector + Cleaner.

Takes the raw Impetus export and:
  1. (LLM) decides which columns describe the *physical attributes of an apparel*
     vs. ids / scores / forecasts / metadata.
  2. Cleans those attributes (casing, mojibake, synonym collapsing) and aggregates
     the rows into distinct cleaned attribute combinations, each with a count, how
     many were flagged trending by Impetus, and sample trend ids for traceback.

The cleaned combos are what Agent 2 reads to find and name trends.
"""
from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from trends.cluster import is_trending
from trends.normalize import normalize

from . import prompts
from .llm import structured_call
from .state import AgentState

# CORE attributes define the dedup signature (low cardinality -> meaningful
# aggregation). Rows sharing the same core tuple collapse into one combo.
CORE_RAW = {
    "Gender": "n_gender",
    "Subcategory": "subcat_family",
    "Color": "color_family",
    "Style": "style_family",
    "Category": "n_category",
}
# DESCRIPTIVE attributes are too granular to split on; they're summarised inside
# each combo as the top few values, so they inform Agent 2 without fragmenting.
DESC_RAW = {
    "Pattern": "n_pattern",
    "Print": "n_pattern",
    "Fabric": "n_fabric",
    "Length": "n_length",
    "Neckline": "n_neckline",
    "Sleeve": "n_sleeve",
}
RAW_TO_SIGNATURE = {**CORE_RAW, **DESC_RAW}
FRIENDLY = {
    "n_gender": "gender", "n_category": "category", "subcat_family": "garment",
    "color_family": "color", "n_pattern": "pattern", "style_family": "style",
    "n_fabric": "fabric", "n_length": "length", "n_neckline": "neckline",
    "n_sleeve": "sleeve",
}


def _top_values(s, n: int = 3) -> str:
    s = s[s.astype(str).str.strip() != ""]
    return ", ".join(s.value_counts().head(n).index) if len(s) else "-"

class AttributeSelection(BaseModel):
    attribute_columns: list[str]
    reasoning: str


def _schema_preview(df: pd.DataFrame, n_samples: int = 5) -> str:
    lines = []
    for c in df.columns:
        vals = df[c].astype(str).str.strip()
        nonempty = vals[vals != ""]
        fill = int(round(100 * len(nonempty) / max(len(df), 1)))
        samples = list(pd.unique(nonempty))[:n_samples]
        lines.append(f"- {c}  (filled {fill}%)  e.g. {samples}")
    return "\n".join(lines)


def run(state: AgentState) -> AgentState:
    raw = pd.read_csv(state["input_path"], encoding="utf-8", dtype=str).fillna("")
    preview = _schema_preview(raw)

    # 1. LLM selects the apparel-attribute columns (prompts live in prompts.yaml).
    sel: AttributeSelection = structured_call(
        prompts.fmt("agent1.select_columns", preview=preview),
        AttributeSelection, system=prompts.get("agent1.system"),
        name="agent1_select_columns", temperature=0.1,
    )

    # Keep only selected columns we know how to clean (robustness guard).
    chosen = [c for c in sel.attribute_columns if c in RAW_TO_SIGNATURE]
    if not chosen:  # fallback to the full known attribute set
        chosen = list(RAW_TO_SIGNATURE)

    # 2. Clean + aggregate into distinct attribute combinations.
    norm = normalize(raw)
    norm["_is_trending"] = is_trending(norm)
    scope = norm[norm["_is_trending"]] if state.get("trending_only", True) else norm

    # 2a. Category-level baseline (Gender × Category bucket, computed on the full
    # dataset so each combo can be compared to its competitive peer group, not just
    # the trending subset).
    norm["_cs"] = pd.to_numeric(norm["Current_Score"], errors="coerce")
    norm["_sc"] = pd.to_numeric(norm["Score_Change_1Mo"], errors="coerce")
    _cs_pos = norm["_cs"].where(norm["_cs"] > 0)  # NaN where score == 0
    norm["_vel"] = norm["_sc"] / _cs_pos           # NaN propagates for zero-score rows
    cat_stats: dict[tuple, dict] = {}
    for (gender, category), g in norm.groupby(["n_gender", "n_category"], dropna=False):
        cat_stats[(gender, category)] = {
            "cat_mean_score": round(float(g["_cs"].mean()), 3),
            "cat_mean_velocity": round(float(g["_vel"].mean(skipna=True)), 4),
            "cat_pct_rising": round(float(
                (g["Recent_Momentum"].str.strip().str.lower() == "rising").mean() * 100
            ), 1),
            "cat_size": int(len(g)),
        }

    def _ordered_unique(raw_map):
        out, seen = [], set()
        for col in chosen:
            f = raw_map.get(col)
            if f and f not in seen:
                seen.add(f)
                out.append(f)
        return out

    # Group on the coarse CORE signature; summarise DESCRIPTIVE attrs per combo.
    core_fields = _ordered_unique(CORE_RAW) or ["n_gender", "subcat_family",
                                                "color_family", "style_family"]
    desc_fields = _ordered_unique(DESC_RAW)

    # Pre-compute velocity per row: Score_Change_1Mo / Current_Score.
    # Rows with Current_Score == 0 are excluded (no demand base to accelerate from).
    # Velocity > 0 means demand is accelerating faster than current level implies.
    def _compute_velocity(df_group: pd.DataFrame) -> float:
        cs = pd.to_numeric(df_group["Current_Score"], errors="coerce")
        sc = pd.to_numeric(df_group["Score_Change_1Mo"], errors="coerce")
        valid = cs[cs > 0]
        if valid.empty:
            return 0.0
        sc_valid = sc.loc[valid.index]
        return float((sc_valid / valid).mean())

    records = []
    for combo_id, (key_vals, g) in enumerate(scope.groupby(core_fields, dropna=False), 1):
        key_vals = key_vals if isinstance(key_vals, tuple) else (key_vals,)
        rec = {"combo_id": combo_id}
        for field, val in zip(core_fields, key_vals):
            rec[FRIENDLY.get(field, field)] = val or "-"
        for field in desc_fields:
            rec[FRIENDLY.get(field, field)] = _top_values(g[field])
        rec["count"] = int(len(g))
        rec["n_trending"] = int(g["_is_trending"].sum())
        # Transparent momentum breakdown straight from Impetus's own labels,
        # so downstream momentum is explainable (not a black-box score).
        al = g["Alert_Type"].astype(str).str.strip().str.lower()
        rec["n_consistently_rising"] = int((al == "consistently rising").sum())
        rec["n_breakout_star"] = int((al == "breakout star").sum())
        # Recent_Momentum is numeric in current exports; fall back to text for legacy.
        from trends.cluster import MOMENTUM_THRESHOLD
        mom_numeric = pd.to_numeric(g["Recent_Momentum"], errors="coerce")
        if mom_numeric.notna().mean() > 0.5:
            rec["n_rising_momentum"] = int((mom_numeric > MOMENTUM_THRESHOLD).sum())
        else:
            rec["n_rising_momentum"] = int(
                g["Recent_Momentum"].astype(str).str.strip().str.lower().eq("rising").sum()
            )
        rec["sample_trend_ids"] = g["Trend_ID"].head(5).tolist()
        # Impetus forecast signals for validity window derivation in postprocess.
        # peak_month: latest peak across member rows (most conservative end-date).
        # trajectory_summary: most common pattern (modal) across member rows.
        peak_vals = g["Peak_Month"].astype(str).str.strip()
        peak_vals = peak_vals[peak_vals.str.match(r"^\d{4}-\d{2}$")]
        rec["peak_month"] = str(peak_vals.max()) if not peak_vals.empty else ""
        traj_vals = g["Trajectory_Summary"].astype(str).str.strip()
        traj_vals = traj_vals[traj_vals != ""]
        rec["trajectory_summary"] = str(traj_vals.mode().iat[0]) if not traj_vals.empty else ""
        # Demand velocity: mean(Score_Change_1Mo / Current_Score) across member rows.
        # Positive = demand accelerating relative to current level.
        rec["velocity_score"] = round(_compute_velocity(g), 4)

        # Bucket ranking signals — all directly from Impetus's normalized scores.
        # Predicted_Score_NMo is a popularity share (0-1, sums to 1 per forecast
        # month across all trends), so comparing within a bucket is meaningful.
        pred1  = pd.to_numeric(g["Predicted_Score_1Mo"], errors="coerce")
        pred2  = pd.to_numeric(g["Predicted_Score_2Mo"], errors="coerce")
        pred3  = pd.to_numeric(g["Predicted_Score_3Mo"], errors="coerce")
        pred4  = pd.to_numeric(g["Predicted_Score_4Mo"], errors="coerce")
        sc1    = pd.to_numeric(g["Score_Change_1Mo"],    errors="coerce")
        conf   = pd.to_numeric(g["Confidence_Score"],    errors="coerce")
        mean_4mo = pd.concat([pred1, pred2, pred3, pred4], axis=1).mean(axis=1).mean()
        rec["_rank_pred1mo"]      = float(pred1.mean())        # near-term forecast (w=0.4)
        rec["_rank_mean4mo"]      = float(mean_4mo)            # sustained 4-month strength (w=0.3)
        rec["_rank_score_change"] = float(sc1.mean())          # current momentum (w=0.2)
        rec["_rank_confidence"]   = float(conf.mean())         # forecast reliability (w=0.1)
        # Subcategory for bucket key (raw column, before normalization mapping)
        rec["_subcategory"] = g["Subcategory"].astype(str).str.strip().mode().iat[0] if not g.empty else ""

        # Category context: how this combo compares to its Gender x Category bucket.
        bucket = cat_stats.get((rec.get("gender", ""), rec.get("category", "")), {})
        if bucket:
            combo_score = float(
                pd.to_numeric(g["Current_Score"], errors="coerce").mean()
            )
            score_vs_cat = round(combo_score - bucket["cat_mean_score"], 3)
            vel_vs_cat = round(rec["velocity_score"] - bucket["cat_mean_velocity"], 4)
            direction = "above" if score_vs_cat >= 0 else "below"
            vel_direction = "faster" if vel_vs_cat >= 0 else "slower"
            rec["category_context"] = (
                f"{rec.get('gender','')} {rec.get('category','')} bucket: "
                f"mean_score={bucket['cat_mean_score']} ({direction} by {abs(score_vs_cat)}), "
                f"mean_velocity={bucket['cat_mean_velocity']} ({vel_direction} by {abs(vel_vs_cat)}), "
                f"pct_rising={bucket['cat_pct_rising']}%, "
                f"bucket_size={bucket['cat_size']} items"
            )
        else:
            rec["category_context"] = ""
        records.append(rec)

    # ── Bucket ranking: Gender × Subcategory ────────────────────────────────
    # Rank each combo within its (gender, subcategory) bucket using four
    # Impetus signals (equal weight, all transparent and directly from the data):
    #   1. final_score          — current demand strength (brand-adjusted)
    #   2. breakout_probability — near-term breakout chance (1-month horizon)
    #   3. score_change_1mo     — momentum direction
    #   4. confidence_score     — forecast reliability
    # Each signal is min-max normalised within its bucket so they're on the
    # same 0-1 scale before averaging.  rank_basis shows the raw values so
    # the rank is fully explainable.
    from collections import defaultdict
    import math

    def _minmax(vals: list[float]) -> list[float]:
        lo, hi = min(vals), max(vals)
        if math.isclose(lo, hi):
            return [0.5] * len(vals)
        return [(v - lo) / (hi - lo) for v in vals]

    bucket_groups: dict[tuple, list[dict]] = defaultdict(list)
    for rec in records:
        key = (rec.get("gender", ""), rec.get("_subcategory", ""))
        bucket_groups[key].append(rec)

    for (gender, subcat), grp in bucket_groups.items():
        for sig in ("_rank_pred1mo", "_rank_mean4mo",
                    "_rank_score_change", "_rank_confidence"):
            vals = [r[sig] if not math.isnan(r[sig]) else 0.0 for r in grp]
            normed = _minmax(vals)
            for rec, nv in zip(grp, normed):
                rec[f"{sig}_n"] = nv

        for rec in grp:
            # Weighted: near-term forecast 40%, sustained 4mo 30%, momentum 20%, confidence 10%
            rec["bucket_rank_score"] = round(
                0.4 * rec["_rank_pred1mo_n"] +
                0.3 * rec["_rank_mean4mo_n"] +
                0.2 * rec["_rank_score_change_n"] +
                0.1 * rec["_rank_confidence_n"], 4
            )
            rec["rank_basis"] = (
                f"predicted_score_1mo={rec['_rank_pred1mo']:.4f} (w=0.4) | "
                f"mean_4mo_score={rec['_rank_mean4mo']:.4f} (w=0.3) | "
                f"score_change={rec['_rank_score_change']:+.4f} (w=0.2) | "
                f"confidence={rec['_rank_confidence']:.4f} (w=0.1)"
            )

        grp.sort(key=lambda r: r["bucket_rank_score"], reverse=True)
        for rank, rec in enumerate(grp, 1):
            rec["bucket_rank"] = rank
            rec["bucket_size"] = len(grp)
            rec["bucket_label"] = f"{gender} × {subcat}"

    # Clean up temp working columns
    for rec in records:
        for col in ("_rank_pred1mo", "_rank_mean4mo", "_rank_score_change", "_rank_confidence",
                    "_rank_pred1mo_n", "_rank_mean4mo_n", "_rank_score_change_n",
                    "_rank_confidence_n", "_subcategory"):
            rec.pop(col, None)

    # Sort globally by bucket_rank_score for display; velocity_rank preserved as secondary.
    records.sort(key=lambda r: r.get("bucket_rank_score", 0), reverse=True)
    for rank, rec in enumerate(records, 1):
        rec["velocity_rank"] = rank
    velocities = [r["velocity_score"] for r in records]
    nonzero = [v for v in velocities if v > 0]
    print(f"[agent1] attribute columns -> {chosen}")
    print(f"[agent1] core signature -> {core_fields}")
    print(f"[agent1] {len(scope):,} rows in scope -> {len(records)} cleaned attribute combos")
    print(f"[agent1] velocity_score: {len(nonzero)}/{len(records)} combos accelerating, "
          f"top3={[round(v, 4) for v in velocities[:3]]}")
    print(f"[agent1] bucket rankings (Gender x Subcategory, top combo per bucket):")
    shown = set()
    for rec in records:
        lbl = rec.get("bucket_label", "")
        if lbl and lbl not in shown:
            shown.add(lbl)
            print(f"  {lbl}: {rec.get('bucket_size',0)} combos | "
                  f"#1 score={rec.get('bucket_rank_score',0):.3f} | {rec.get('rank_basis','')}")
    print(f"[agent1] category baselines (Gender x Category):")
    for (gender, cat), stats in sorted(cat_stats.items()):
        print(f"  {gender} x {cat}: mean_score={stats['cat_mean_score']}, "
              f"mean_vel={stats['cat_mean_velocity']}, pct_rising={stats['cat_pct_rising']}%, "
              f"size={stats['cat_size']}")

    return {
        "schema_preview": preview,
        "attribute_columns": chosen,
        "column_reasoning": sel.reasoning,
        "cleaned_records": records,
    }
