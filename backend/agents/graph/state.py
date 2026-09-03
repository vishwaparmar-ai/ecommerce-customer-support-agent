from __future__ import annotations

from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]

    customer_id: str
    conversation_id: str

    intent: Optional[str]
    intent_confidence: Optional[float]

    retrieved_context: Optional[list[dict]]

    tool_calls: list[dict]

    # Approval state
    requires_approval: bool
    approved: Optional[bool]

    # ---------------------------------------------------------
    # Pending high-impact action
    # ---------------------------------------------------------
    #
    # When an action pauses for confirmation, we store the
    # exact order being acted upon here.
    #
    # This is important because LangGraph re-runs the node
    # after Command(resume=...).
    #
    pending_order_id: Optional[str]

    escalated: bool


def new_agent_state(
    customer_id: str,
    conversation_id: str,
) -> AgentState:

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
        pending_order_id=None,
        escalated=False,
    )