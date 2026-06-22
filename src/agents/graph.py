"""The 3-agent LangGraph:  Agent 1 -> Agent 2 -> Agent 3.

    attribute_selector  (Agent 1: pick + clean apparel attributes)
        -> trend_namer  (Agent 2: group + name trends, with market/social context)
        -> trend_classifier (Agent 3: festive / event_based / functional / attribute_driven)

Each node is wrapped with Langfuse @observe so the whole run is one trace with a
span per agent (when Langfuse keys are set).
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from . import agent1_attributes, agent2_namer, agent3_classifier
from .state import AgentState

try:
    from langfuse import observe
except Exception:  # pragma: no cover - tracing optional
    def observe(*args, **kwargs):
        def deco(fn):
            return fn
        return deco(args[0]) if args and callable(args[0]) else deco


@observe(name="agent1_attribute_selector")
def _agent1(state: AgentState) -> AgentState:
    return agent1_attributes.run(state)


@observe(name="agent2_trend_namer")
def _agent2(state: AgentState) -> AgentState:
    return agent2_namer.run(state)


@observe(name="agent3_trend_classifier")
def _agent3(state: AgentState) -> AgentState:
    return agent3_classifier.run(state)


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("attribute_selector", _agent1)
    g.add_node("trend_namer", _agent2)
    g.add_node("trend_classifier", _agent3)

    g.add_edge(START, "attribute_selector")
    g.add_edge("attribute_selector", "trend_namer")
    g.add_edge("trend_namer", "trend_classifier")
    g.add_edge("trend_classifier", END)
    return g.compile()
