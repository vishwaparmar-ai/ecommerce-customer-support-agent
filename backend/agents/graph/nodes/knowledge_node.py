"""
Graph node: knowledge_node.

Destination for the "knowledge" route (policy_question intent). Wraps
backend.rag.qa_chain.answer_policy_question -- same "thin adapter, not
new logic" pattern as classify_intent_node.

Unlike classify_intent_node, this node DOES append to messages -- its
output is the actual customer-facing answer, not internal bookkeeping.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from backend.rag.qa_chain import answer_policy_question
from backend.agents.graph.state import AgentState


def _get_latest_human_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No HumanMessage found in state -- knowledge_node needs at least one.")


def knowledge_node(state: AgentState) -> dict:
    """
    Answers the customer's policy question using the RAG chain, appends
    the answer as an AIMessage, and stores the sources used in
    retrieved_context so a later validation step (or the final response)
    can reference or cite them.
    """
    question = _get_latest_human_message(state)
    result = answer_policy_question(question)


    return {
        "messages": [AIMessage(content=result.answer)],
        "retrieved_context": result.sources,
    }