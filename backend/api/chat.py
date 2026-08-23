"""
Conversation endpoints, matching the real API shape from the project doc
(section 9): POST /conversations creates a conversation, POST
/conversations/{id}/messages sends a message to the agent.

UPDATED for cancellation_node's real approval gate: this now detects when
the graph PAUSES (interrupt() was called) vs. produced a final answer, and
supports resuming a paused conversation. Conversation history is no longer
tracked manually here -- it comes from the graph's own checkpointer
(keyed by conversation_id as the thread_id), which is a big part of why
the checkpointer was added to graph_builder.py in the first place.

STAND-IN NOTE: there's still no real Conversation/Message database table
(full Phase 6 persistence) -- _conversations here just tracks which
conversation_ids exist and whether each is currently "active" or "paused"
(awaiting confirmation). The actual message content lives in
InMemorySaver's in-memory state, not a database -- still lost on server
restart, still not safe across multiple worker processes. Replace with
real DB-backed tracking + a persisted checkpointer for production.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user
from backend.db.models import Customer
from backend.agents.graph.graph_builder import build_graph

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)

# conversation_id -> "active" | "paused". See module docstring for why
# this is still an in-memory stand-in rather than a real DB table.
_conversations: dict[str, str] = {}


class CreateConversationRequest(BaseModel):
    channel: str = "web"


class SendMessageRequest(BaseModel):
    message: str


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: CreateConversationRequest,
    current_user: Customer = Depends(get_current_user),
):
    conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    _conversations[conversation_id] = "active"
    return {"conversation_id": conversation_id, "status": "active"}


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: str,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    if conversation_id not in _conversations:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    compiled_graph = build_graph(db, current_user)
    config = {"configurable": {"thread_id": conversation_id}}

    if _conversations[conversation_id] == "paused":
        # A previous call hit interrupt() -- treat this message as the
        # customer's confirmation response, not a new question.
        result = compiled_graph.invoke(Command(resume=payload.message), config=config)
    else:
        result = compiled_graph.invoke(
            {
                "customer_id": str(current_user.id),
                "conversation_id": conversation_id,
                "messages": [HumanMessage(content=payload.message)],
            },
            config=config,
        )

    if "__interrupt__" in result:
        # The graph paused -- surface the interrupt payload and mark this
        # conversation as awaiting confirmation.
        _conversations[conversation_id] = "paused"
        interrupt_payload = result["__interrupt__"][0].value
        return {
            "conversation_id": conversation_id,
            "requires_confirmation": True,
            "confirmation_request": interrupt_payload,
        }

    _conversations[conversation_id] = "active"
    return {
        "conversation_id": conversation_id,
        "answer": result["messages"][-1].content,
        "intent": result.get("intent"),
    }