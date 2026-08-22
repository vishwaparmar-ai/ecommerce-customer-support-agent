"""
State Schema :
Every node in the graph receives this state and returns a partial update
to it. This is the single most important thing to get right before
writing any nodes -- every node's signature depends on this shape.
"""

from __future__ import annotations
 
from typing import Annotated, Optional
 
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

class AgentState(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]
    customer_id: str
 
    # LangGraph checkpointer thread key. Not a DB foreign key (yet) --
    conversation_id: str
 
    # Set by the classify_intent node. Optional because it's None before
    # that node has run.
    intent: Optional[str]
    intent_confidence: Optional[float]
 
    # Set by the RAG node when a policy_question is answered -- kept so a
    # later validation step or the final response can reference sources.
    retrieved_context: Optional[list[dict]]
 
    # Trace of every tool call made this turn: [{"name": ..., "args": ...,
    # "result": ...}, ...]. Useful for debugging, response validation, and
    # eventually the audit log Phase 9 wants.
    tool_calls: list[dict]
 
    # Approval-gate hooks for high-impact actions (cancel_order today,
    # anything similar later). A node can set requires_approval=True and
    # pause; `approved` gets set once the customer actually confirms.
    requires_approval: bool
    approved: Optional[bool]
 
    # Set by an escalation path -- lets the graph short-circuit to an
    # escalation/end node regardless of which intent path it came from.
    escalated: bool

def new_agent_state(customer_id: str, conversation_id: str) -> AgentState:
    """
    Builds a fresh AgentState for the start of a graph run. Call this once
    per invocation and pass the authenticated customer_id in -- never let
    a node or the model set customer_id itself.
    """
    return AgentState(
        messages=[],
        customer_id=customer_id,
        conversation_id=conversation_id,
        intent=None,
        intent_confidence=None,
        retrieved_context=None,
        tool_calls=[],
        requires_approval=False,
        approved=None,
        escalated=False,
    )
