"""
Graph builder -- wires together everything built so far into an actual
compiled LangGraph, for real end-to-end testing.

Currently wired: classify_intent -> route_by_intent -> {knowledge_node,
order_node}. Routes to return/refund/cancellation/escalation intents hit
a placeholder node instead of a real implementation, since those nodes
don't exist yet -- this lets you test what IS built without the whole
graph being blocked on finishing every path first.

No checkpointer yet (no persistence across turns, no interrupt() support)
-- that comes with Phase 6 memory and the cancellation_node's approval
gate. Each call to run_graph is a fresh, single-turn conversation.
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session
from backend.db.models import Customer
from backend.agents.graph.state import AgentState, new_agent_state
from backend.agents.graph.routing import route_by_intent, INTENT_ROUTE_MAP
from backend.agents.graph.nodes.classify_intent_node import classify_intent_node
from backend.agents.graph.nodes.knowledge_node import knowledge_node
from backend.agents.graph.nodes.order_node import make_order_node


def _not_implemented_node(state: AgentState) -> dict:
    """
    Placeholder for return/refund/cancellation/escalation routes until
    those nodes are built. Says so honestly rather than pretending to
    handle the request.
    """
   
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
    """
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("knowledge_node", knowledge_node)
    graph.add_node("order_node", make_order_node(db, current_user))
    graph.add_node("not_implemented_node", _not_implemented_node)

    graph.add_edge(START, "classify_intent")

    # Route map currently sends return/refund/cancellation/escalation to
    # the placeholder -- swap these to real node names as they're built.
    path_map = {
        "knowledge": "knowledge_node",
        "order": "order_node",
        "return": "not_implemented_node",
        "refund": "not_implemented_node",
        "cancellation": "not_implemented_node",
        "escalation": "not_implemented_node",
    }
    graph.add_conditional_edges("classify_intent", route_by_intent, path_map)

    graph.add_edge("knowledge_node", END)
    graph.add_edge("order_node", END)
    graph.add_edge("not_implemented_node", END)

    return graph.compile()


def run_graph(db: Session, current_user: Customer, message: str, conversation_id: str | None = None) -> dict:
    """
    Convenience entry point: builds the graph, runs one message through
    it, and returns the final answer plus some debug info (intent, tool
    trace) -- useful while testing via Swagger.
    """
    conversation_id = conversation_id or str(uuid.uuid4())
    compiled_graph = build_graph(db, current_user)

    initial_state = new_agent_state(customer_id=str(current_user.id), conversation_id=conversation_id)
    initial_state["messages"] = [HumanMessage(content=message)]

    final_state = compiled_graph.invoke(initial_state)

    # The last message in the final state is the answer to show the customer.
    final_answer = final_state["messages"][-1].content

    return {
        "answer": final_answer,
        "intent": final_state.get("intent"),
        "intent_confidence": final_state.get("intent_confidence"),
        "tool_calls": final_state.get("tool_calls", []),
        "conversation_id": conversation_id,
    }