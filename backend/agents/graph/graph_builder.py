"""
Graph builder -- wires together everything built so far into an actual
compiled LangGraph, for real end-to-end testing.

CHECKPOINTER: now backed by Postgres (langgraph-checkpoint-postgres),
replacing the earlier InMemorySaver. This is the Phase 6 upgrade --
conversation/interrupt state now survives a server restart, since it's
stored in the same Postgres database as everything else, not this
process's RAM.

Install: pip install langgraph-checkpoint-postgres
Security: set LANGGRAPH_STRICT_MSGPACK=true in your .env -- this
restricts checkpoint deserialization to known-safe types, which matters
if your database were ever compromised (per the library's own docs).

_checkpointer is still a MODULE-LEVEL singleton, same reasoning as
before: a fresh connection/setup on every build_graph() call would be
wasteful (and .setup() should only need to run once per process, not
per request). This holds ONE persistent psycopg connection for the life
of the process -- fine for local dev and testing, but production should
use a connection pool (psycopg_pool.ConnectionPool) instead of a single
bare connection, and ideally tie setup/teardown to FastAPI's lifespan
events rather than running at import time.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from backend.core.config import settings
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

# PostgresSaver.from_conn_string() expects a plain libpq-style URI
# ("postgresql://..."), not SQLAlchemy's dialect+driver style
# ("postgresql+psycopg://..."). Strip the driver suffix.
_CHECKPOINTER_DB_URI = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")

# .from_conn_string() is a context manager; entering it here and never
# exiting keeps one connection open for the process lifetime -- see the
# module docstring's production caveat about using a real pool instead.
_checkpointer_cm = PostgresSaver.from_conn_string(_CHECKPOINTER_DB_URI)
_checkpointer = _checkpointer_cm.__enter__()
_checkpointer.setup()  # idempotent: creates checkpoint tables if they don't exist yet


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