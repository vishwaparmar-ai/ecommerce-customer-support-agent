"""
Graph builder -- wires together everything built so far into an actual
compiled LangGraph, for real end-to-end testing.

Now includes a real checkpointer (InMemorySaver), required for
cancellation_node's interrupt()/Command(resume=...) approval gate --
without a checkpointer there is no saved state to pause and resume from.
This also happens to be an early, minimal version of what Phase 6 (memory)
formally builds: conversation state persisted across turns, keyed by
thread_id, instead of your own hand-rolled history tracking.

IMPORTANT: _checkpointer is a MODULE-LEVEL singleton, not created fresh
inside build_graph(). InMemorySaver only holds state in this process's
memory -- if you created a new one on every build_graph() call, a paused
conversation's state would vanish the instant the next request rebuilt
the graph, breaking resume entirely. Same limitation as the in-memory
conversations dict from before: lost on server restart, not safe across
multiple worker processes. Replace with a real persisted checkpointer
(e.g. a Postgres-backed one) when this goes beyond local testing.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.db.models import Customer
from backend.agents.graph.state import AgentState
from backend.agents.graph.routing import route_by_intent
from backend.agents.graph.nodes.classify_intent_node import classify_intent_node
from backend.agents.graph.nodes.knowledge_node import knowledge_node
from backend.agents.graph.nodes.order_node import make_order_node
from backend.agents.graph.nodes.return_node import make_return_node
from backend.agents.graph.nodes.refund_node import make_refund_node
from backend.agents.graph.nodes.escalation_node import make_escalation_node
from backend.agents.graph.nodes.cancellation_node import make_cancellation_node
from backend.agents.graph.nodes.response_validator_node import response_validator_node

_checkpointer = InMemorySaver()


def _not_implemented_node(state: AgentState) -> dict:
    """
    Placeholder for return/refund/cancellation/escalation routes until
    those nodes are built. Says so honestly rather than pretending to
    handle the request.
    """
    logger.info(
        "graph_node_not_implemented_hit",
        extra={"customer_id": state["customer_id"], "intent": state.get("intent")},
    )
    return {
        "messages": [
            AIMessage(
                content=(
                    f"I can see this is a '{state.get('intent')}' request, but that "
                    f"part of my capabilities isn't built yet in this test graph."
                )
            )
        ]
    }


def build_graph(db: Session, current_user: Customer):
    """
    Builds and compiles the graph fresh for one request, scoped to
    current_user -- same reasoning as every tool/node factory: identity
    gets bound at build time, not left for the model or state to supply.
    Compiling fresh each call is cheap and does NOT lose checkpoint data --
    _checkpointer is shared at module level regardless of how many times
    this function runs.
    """
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("knowledge_node", knowledge_node)
    graph.add_node("order_node", make_order_node(db, current_user))
    graph.add_node("return_node", make_return_node(db, current_user))
    graph.add_node("refund_node", make_refund_node(db, current_user))
    graph.add_node("escalation_node", make_escalation_node(db, current_user))
    graph.add_node("cancellation_node", make_cancellation_node(db, current_user))
    graph.add_node("not_implemented_node", _not_implemented_node)
    graph.add_node("response_validator", response_validator_node)

    graph.add_edge(START, "classify_intent")

    # All six intents now have real nodes.
    path_map = {
        "knowledge": "knowledge_node",
        "order": "order_node",
        "return": "return_node",
        "refund": "refund_node",
        "cancellation": "cancellation_node",
        "escalation": "escalation_node",
    }
    graph.add_conditional_edges("classify_intent", route_by_intent, path_map)

    # Every path now goes through response_validator before END -- the
    # final safety check on section 12's workflow diagram.
    graph.add_edge("knowledge_node", "response_validator")
    graph.add_edge("order_node", "response_validator")
    graph.add_edge("return_node", "response_validator")
    graph.add_edge("refund_node", "response_validator")
    graph.add_edge("escalation_node", "response_validator")
    graph.add_edge("cancellation_node", "response_validator")
    graph.add_edge("not_implemented_node", "response_validator")
    graph.add_edge("response_validator", END)

    return graph.compile(checkpointer=_checkpointer)