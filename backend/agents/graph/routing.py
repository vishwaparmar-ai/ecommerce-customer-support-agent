"""
Graph routing: route_by_intent.

The conditional edge that reads state["intent"] (set by classify_intent_node)
and decides which node runs next. This is the actual "decision" that
simple_agent.py left to the model's judgment -- here it's a plain,
deterministic Python function, which is the whole point of Phase 5.

Used with graph.add_conditional_edges(source="classify_intent",
path=route_by_intent, path_map=INTENT_ROUTE_MAP).
"""

from __future__ import annotations

from backend.schemas.intent_classification import Intent
from backend.agents.graph.state import AgentState

# Maps each possible return value of route_by_intent to the actual node
# name it should go to. Pass this as path_map when wiring the conditional
# edge -- LangGraph needs both the function and this map to build the
# graph's edges correctly.
INTENT_ROUTE_MAP = {
    "knowledge": "knowledge_node",
    "order": "order_node",
    "return": "return_node",
    "refund": "refund_node",
    "cancellation": "cancellation_node",
    "escalation": "escalation_node",
}

_INTENT_TO_ROUTE = {
    Intent.POLICY_QUESTION.value: "knowledge",
    Intent.ORDER_STATUS.value: "order",
    Intent.RETURN_REQUEST.value: "return",
    Intent.REFUND_REQUEST.value: "refund",
    Intent.CANCELLATION.value: "cancellation",
    Intent.SUPPORT_OTHER.value: "escalation",
}


def route_by_intent(state: AgentState) -> str:
    """
    Returns one of INTENT_ROUTE_MAP's keys based on state["intent"].
    Falls back to "escalation" for any intent this map doesn't recognize
    (e.g. the classifier schema changes later and a route is missed) --
    fail toward a human, not toward silently picking an arbitrary path.
    """
    if state.get("escalated"):
        return "escalation"

    intent = state.get("intent")
    return _INTENT_TO_ROUTE.get(intent, "escalation")