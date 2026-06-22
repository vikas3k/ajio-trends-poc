# AJIO Trend Generation — Implementation Plan & Status

Plan mapped to the product PRD (`AJIO_Trend_Generation_Requirements_DS.docx`),
covering **only the trend-generation scope** (personalization & user-segment
mapping are explicitly out of scope per direction). Reflects what this repo
currently does and what remains.

**Legend:** ✅ done · 🟡 partial · ⬜ not started · ⛔ out of scope (by instruction)

---

## 0. What exists in the repo today

Two systems were built over the course of the POC:

1. **Agentic system (PRD-aligned, current)** — `src/agents/`, run via `run_agents.py`.
   A LangGraph 3-agent graph on Gemini 2.5 Pro (Vertex AI), traced in Langfuse:
   - Agent 1 `attribute_selector` — LLM picks apparel-attribute columns, cleans &
     aggregates Impetus rows into attribute combos.
   - Agent 2 `trend_namer` — multi-source generation: grounded social/LLM research
     → buzzword dictionary → attribute trends (Impetus) → occasion/event/functional
     trends (LLM). Buzzword-first naming, 3–5 candidates each.
   - Agent 3 `trend_classifier` — assigns the PRD 4-category taxonomy.
   - Outputs: `output/agentic_trends.csv`, `output/buzzword_dictionary.csv`.

2. **Rule-based pipeline (earlier, deterministic)** — `src/trends/`, run via
   `build_themes.py` / `run_pipeline.py`. Normalizes Impetus, filters to
   Impetus-trending rows, groups into themes, names them. Kept as a deterministic
   reference; superseded by the agentic system for PRD work.

---

## 1. PRD §3 — Trend Taxonomy (4 categories)  ✅

**Done:** Agent 3 classifies every trend into the PRD's exact taxonomy —
`attribute_driven | occasion_festival | event_driven | functional` — with PRD
definitions/examples and a priority cascade (festival → event → functional →
attribute fallback). Last run spanned all four categories.

**What else can be done**
- Add a **classification confidence** and allow **secondary category** (a trend
  can be both functional and attribute_driven).
- Build a small **human-labelled eval set** to measure classification accuracy and
  catch drift between runs.

## 2. PRD §4 — Trend Name Generation  🟡

**Done:** Names are customer-facing, **buzzword-first** (real circulating buzzwords
preferred over invented coinages, per "unknown coined phrases won't perform"), and
each trend carries **3–5 candidate names** for review. Naming principles
(understandable / jazzy / inviting / contextually familiar / not vanilla) are
enforced in the prompt.

**What else can be done**
- 🟡 **Human review checkpoint is not a workflow yet** — candidates are just CSV
  columns. Add an explicit `review_status` (pending/approved/rejected) +
  `approved_name` field and a lightweight review surface (Google Sheet / Streamlit).
- **Brand-safety / profanity / trademark filter** on candidate names before review.
- **Performance feedback loop**: capture click-through once trends are live and
  learn which name styles perform (the PRD's core "inviting to click" goal).

## 3. PRD §6.1 — Impetus (attribute signal)  ✅

**Done:** Ingest the monthly Impetus export, clean (casing, mojibake, synonym
collapsing), aggregate into attribute combos → attribute_driven trends
(`source=impetus`).

**What else can be done**
- Use the **Impetus forecast/momentum columns** (currently unused) as a
  *transparent* input to validity windows and ranking.
- Handle **monthly refresh + schema drift** (column renames, new attributes).

## 4. PRD §6.2 — LLM Querying (occasion / event / functional)  ✅

**Done:** Agent 2 generates `occasion_festival`, `event_driven`, and `functional`
trends for the current Indian calendar window (`source=llm`), grounded in live
search — the categories Impetus can't supply.

**What else can be done**
- Replace the inline calendar with a **data-driven festival/occasion calendar**
  (dated India festival list per year) so windows are exact, not model-recalled.
- **Per-category prompt tuning** and cross-run **dedup** so the same trend isn't
  regenerated under slightly different names each cycle.

## 5. PRD §6.3 — Social & Fashion Media Crawl (buzzwords)  🟡

**Done (approximation):** Live Google-Search grounding → a **buzzword dictionary**
(`buzzword_dictionary.csv`, buzzword → attributes → likely category), which is then
mapped onto attribute trends (`source=social_crawl`).

**What else can be done — this is the biggest real gap**
- The PRD wants a **scheduled crawler over a curated source list** (Instagram
  hashtags, Pinterest boards, Vogue/Elle India, fashion blogs) with keyword/
  hashtag extraction. Grounding is a stand-in, not a maintained crawl pipeline.
  Options: build the crawler, or use a social-listening / trends API vendor.
- **Persist the buzzword dictionary over time** and attach a **volume/momentum**
  signal per buzzword (how hot, rising/falling) — needed for ranking & validity.

## 6. PRD §8 — End-to-End Pipeline (stage-by-stage)

| Stage | Status | Notes |
|---|---|---|
| 1. Signal ingestion (Impetus + LLM + social) | ✅ / 🟡 | social = grounding, not a crawler |
| 2. Trend classification | ✅ | PRD 4-category |
| 3. Name generation (3–5 candidates) | ✅ | buzzword-first |
| 4. Buzzword mapping | ✅ | dictionary + `source` tag |
| 5. Segment tagging | ⛔ | out of scope (personalization) |
| 6. Validity scoring | 🟡 | `validity_window` for context trends; `priority_score` deliberately omitted (user rejected opaque scores) |
| 7. Review & publish | ⬜ | no review/approval workflow or publish step |
| 8. Personalization | ⛔ | out of scope |

**What else can be done**
- **Validity windows** for *attribute* trends (currently blank) via a simple rule
  (e.g. 2–4 weeks) or the Impetus momentum signal.
- A **transparent priority/momentum** field (from Impetus counts + buzzword volume)
  — explainable, unlike the earlier rejected black-box score.
- **Stage 7 review & publish**: approval workflow + a clean published catalogue.

## 7. PRD Objective — "refresh continuously"  ⬜

**What else can be done**
- **Scheduling**: weekly / bi-weekly / event-triggered runs (cron, Airflow, or the
  scheduled-agent mechanism). No scheduler exists yet — runs are manual.
- **Run-over-run state**: persist past trends to dedup, track lifecycle
  (new → rising → peak → fading), and expire stale trends.

## 8. Cross-cutting / engineering

- ✅ **Observability**: Langfuse tracing wired (`.env`, `LANGFUSE_TIMEOUT=20`).
- ⬜ **Eval harness**: no automated quality check on names/classification.
- ⬜ **Consolidation**: decide to retire or formally keep the rule pipeline.
- ⬜ **Config/secrets**: creds live in `.env`/`.gcp` in plaintext — move to a
  secrets manager for anything beyond POC; rotate the shared keys.
- ⬜ **Tests + CI**, packaging, and a README.

## 9. Out of scope (deferred by instruction)  ⛔

PRD §5 (Trend→Segment mapping) and §7 (Personalization / user-segment affinity
model). Documented here so the boundary is explicit; when picked up, they slot in
as Stage 5 (tag each trend with L1+L2 segments) and Stage 8 (per-user filtering).

---

## Recommended next steps (prioritised)

**Near-term (high value, low effort)**
1. Add `review_status` + `approved_name` columns and a review surface (PRD §4/§8.7).
2. Fill attribute-trend `validity_window` via a simple rule; add a transparent
   momentum field from Impetus counts + buzzword volume.
3. Cross-run dedup + a persisted trend store (lifecycle tracking).

**Medium**
4. Replace grounding with (or augment by) a real social-crawl source list /
   trends API, and persist the buzzword dictionary with volume signal (PRD §6.3).
5. Data-driven festival/occasion calendar for §6.2.
6. Scheduling for continuous refresh + a small name/classification eval set.

**Later**
7. CTR feedback loop on live trend names.
8. (If reprioritised) segment tagging + personalization (PRD §5, §7).
