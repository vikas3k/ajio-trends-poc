# Impetus Trend Forecast — Input Data Schema

**Report Month:** June 2026  
**Total Rows:** 32,436 | **Brands:** 25 | **Gender:** Men + Women | **Categories:** Topwear, Bottomwear, Dresses

---

## Mandatory Columns
*These are required for the pipeline to run. Missing or empty values will cause errors.*

| Column | Data Type | Values / Range | Notes |
|---|---|---|---|
| `Trend_ID` | String | e.g. `gap_men_topwear_suits_1` | Unique identifier per row |
| `Gender` | String | `Men` · `Women` | |
| `Category` | String | `Topwear` · `Bottomwear` · `Dresses` | |
| `Subcategory` | String | 56 values — Jeans, T-shirts, Tops, etc. | |
| `Color` | String | 31 values — White, Blue, Black, etc. | |
| `Style` | String | 68 values — Relaxed, Slim, Wide-Leg, etc. | |
| `Fabric` | String | 19 values — Cotton, Linen, Polyester, etc. | |
| `Alert_Type` | String | `Consistently Rising` · `Stable Leaders` · `Long Tail` · `Markdown Candidate` | Primary trending signal |
| `Recent_Momentum` | Float | Positive = accelerating · Negative = slowing | Score Change ÷ Current Score |
| `Current_Score` | Float (0–1) | Higher = stronger current demand | |
| `Confidence_Score` | Float (0–1) | Higher = more reliable forecast | |
| `Predicted_Score_1Mo` | Float (0–1) | Forecast demand — Month 1 (Jul 2026) | Used for bucket ranking |
| `Predicted_Score_2Mo` | Float (0–1) | Forecast demand — Month 2 (Aug 2026) | |
| `Predicted_Score_3Mo` | Float (0–1) | Forecast demand — Month 3 (Sep 2026) | |
| `Predicted_Score_4Mo` | Float (0–1) | Forecast demand — Month 4 (Oct 2026) | |
| `Score_Change_1Mo` | Float | Delta vs current score | Used for velocity |
| `Peak_Month` | String (YYYY-MM) | `2026-07` to `2026-10` | When demand peaks |
| `Trajectory_Summary` | String | e.g. `Rise->Rise->Rise->Rise` | 4-month direction |

---

## Optional Columns
*Used when present to enrich trend output. Pipeline continues without them.*

| Column | Data Type | Values / Range | Used For |
|---|---|---|---|
| `Trend_Description` | String | e.g. `White Plain Cotton Relaxed Suit` | Agent 2 grounding context |
| `Brands` | String | 25 AJIO brand names | Metadata only |
| `Pattern` | String | 35 values — Plain, Floral, Stripes, etc. | Attribute clustering |
| `Print` | String | 55 values — SOLID, Typography, Animal, etc. | Merged with Pattern |
| `Length` | String | 29 values — Regular, Midi, Ankle, etc. | Attribute clustering |
| `Neckline` | String | 31 values — Round Neck, V-Neck, etc. | Attribute clustering |
| `Sleeve` | String | 32 values — Short Sleeve, Sleeveless, etc. | Attribute clustering |
| `Current_Rank` | Integer | Rank within brand | Bucket ranking |
| `Score_Change_4Mo` | Float | Delta vs current at month 4 | Velocity signal |
| `Top_Performer_Today` | String | `Yes` · `No` | Momentum enrichment |
| `Breakout_Likelihood` | String | `High` · `Medium` | Momentum enrichment |
| `Confidence_Level` | String | `High` · `Medium` · `Low` | Metadata |
| `Why_Picked` | String | Free text (19% filled) | Momentum basis text |
| `final_score` | Float | Impetus composite score | Bucket ranking |
| `Report_Month` | String (YYYY-MM) | `2026-06` | Metadata |

---

## Not Used
*Present in the export but not consumed by the pipeline.*

| Column | Reason |
|---|---|
| `P_Rise / P_Decline / P_Flat (1–4Mo)` | 0% fill in this export — not populated by Impetus |
| `Predicted_Rank_1–4Mo` | Rank within brand — less stable than score across exports |
| `Rank_Change_1–4Mo` | Same reason |
| `Direction_1–4Mo` | Covered by `Trajectory_Summary` |
| `Breakout_Probability_1–4Mo` | Partially used in ranking via `Confidence_Score` |
| `brand_view_rank` | Redundant with `final_score` |
| `cohort_n_resolved_peers` | Internal Impetus metadata |
| `Forecast_Month_1–4` | Always fixed months — derived from `Report_Month` |
