# Trend Generation — Code Flow

Agentic system (`run_agents.py`). LangGraph 3-agent graph on Gemini 2.5 Pro
(Vertex AI), traced in Langfuse, with generation-side post-processing.

## Mermaid

```mermaid
flowchart TD
    ENV[".env<br/>Vertex + Langfuse cfg"] --> RUN
    CSV[("Impetus CSV<br/>Trend_Forecast")] --> A1
    GS[("Google Search<br/>grounding")] --> A2

    RUN["run_agents.py<br/>load_dotenv → build_graph → invoke"] --> A1

    subgraph GRAPH["LangGraph graph (state = AgentState)"]
        direction TB
        A1["Agent 1 · attribute_selector<br/>① LLM picks attribute cols<br/>② normalize() clean<br/>③ is_trending() filter<br/>④ group → combos (+momentum breakdown)"]
        A2["Agent 2 · trend_namer<br/>4 Gemini calls (see below)"]
        A3["Agent 3 · trend_classifier<br/>LLM → PRD 4 categories"]
        A1 -->|"cleaned_records"| A2
        A2 -->|"trends + buzzwords + brief"| A3
    end

    subgraph A2STEPS["Agent 2 internals"]
        direction TB
        SA["A. grounded research (+retry)"]
        SB["B. buzzword dictionary<br/>recency / confidence / evidence"]
        SC["C. attribute trends from combos<br/>buzzword-first · 3–5 candidates"]
        SD["D. occasion / event / functional<br/>from calendar + buzzwords"]
        SA --> SB --> SC --> SD
    end
    A2 -.internals.-> A2STEPS

    A3 -->|"classified_trends"| PP

    subgraph PP["postprocess.py (after graph)"]
        direction TB
        E["enrich_trends<br/>momentum + validity + buzzword evidence + review fields"]
        L["apply_lifecycle<br/>dedup + new/rising/peak/fading"]
        E --> L
    end
    L <-->|"read/write"| STORE[("trend_store.json")]

    L --> OUT1["agentic_trends.csv"]
    A2 --> OUT2["buzzword_dictionary.csv"]

    LLM["llm.py · Gemini 2.5 Pro / Vertex<br/>retry · structured / grounded"]
    LF[("Langfuse traces")]
    A1 -. uses .-> LLM
    A2 -. uses .-> LLM
    A3 -. uses .-> LLM
    LLM -. logs .-> LF
```

## ASCII (fallback)

```
.env ─┐
      ▼
Impetus CSV ─► run_agents.py ─► graph.invoke(AgentState)
                                     │
  ┌──────────────────────────────────┴──────────────────────────────────┐
  │ LangGraph                                                             │
  │  Agent 1  attribute_selector                                          │
  │   read CSV → LLM pick attr cols → normalize → is_trending → combos    │
  │      │ cleaned_records (+ momentum breakdown per combo)               │
  │      ▼                                                                │
  │  Agent 2  trend_namer        ◄── Google Search grounding              │
  │   A grounded research  →  B buzzword dict  →  C attribute trends       │
  │                                          →  D occasion/event/functional│
  │      │ trends + buzzwords + brief                                     │
  │      ▼                                                                │
  │  Agent 3  trend_classifier  → PRD 4 categories                        │
  └──────────────────────────────────┬──────────────────────────────────┘
                                      │ classified_trends
                                      ▼
                 postprocess.py:  enrich_trends (momentum/validity/
                                  review/buzzword evidence)
                                  → apply_lifecycle (dedup + lifecycle) ⇄ trend_store.json
                                      │
                                      ▼
                 outputs:  agentic_trends.csv   buzzword_dictionary.csv

  cross-cutting:  llm.py (Gemini/Vertex, retry) ──logs──► Langfuse
```

## PRD source mapping

| Step | PRD source |
|---|---|
| Agent 1 + Agent 2·C (attribute trends) | §6.1 Impetus |
| Agent 2·D (occasion/event/functional)  | §6.2 LLM querying |
| Agent 2·A/B (grounded research → buzzwords) | §6.3 Social crawl (approx.) |
| Agent 3 | §3 Taxonomy |
| postprocess (naming review, validity, momentum) | §4 / §8.6 / §8.7 |
