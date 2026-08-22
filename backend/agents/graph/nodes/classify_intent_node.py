"""
Graph node: classify_intent.

Wraps the existing backend.agents.intent_classifier.classify_intent
function as a LangGraph node. This node does no new reasoning of its own --
it just adapts the state-in/state-out shape LangGraph expects around a
function you already built and tested standalone.

Takes the latest human message from state["messages"], classifies it, and
writes the result back into state["intent"] / state["intent_confidence"]
for the routing edge (built next) to read.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from backend.agents.intent_classifier import classify_intent
from backend.agents.graph.state import AgentState


def _get_latest_human_message(state: AgentState) -> str:
    """
    Finds the most recent HumanMessage in state["messages"]. This node
    only classifies the customer's latest turn, not the whole history --
    multi-turn context awareness (e.g. "and also cancel it" referring to
    an order mentioned two messages ago) is a later refinement, not
    something this node handles yet.
    """
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No HumanMessage found in state -- classify_intent_node needs at least one.")


def classify_intent_node(state: AgentState) -> dict:
    """
    Reads the latest customer message, classifies it, and returns the
    partial state update. Does not append to messages -- this node is
    purely internal bookkeeping, not something the customer sees directly.
    """
    latest_message = _get_latest_human_message(state)
    result = classify_intent(latest_message)


    return {
        "intent": result.intent.value,
        "intent_confidence": result.confidence,
    }