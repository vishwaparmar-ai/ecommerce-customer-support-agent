"""
Conversation endpoints, matching the real API shape from the project doc
(section 9): POST /conversations creates a conversation, POST
/conversations/{id}/messages sends a message to the agent.

STAND-IN NOTE: there's no Conversation/Message database table yet (Phase 6
builds that, plus a real LangGraph checkpointer for state persistence).
Message history here lives in a plain in-memory dict, keyed by
conversation_id. This means:
    - History is lost if the server restarts.
    - It is NOT safe for multiple server workers/processes (each would
      have its own dict).
    - It exists purely so you can see real multi-turn behavior now,
      matching the eventual API shape, without waiting for Phase 6.
Replace _conversations with real DB reads/writes once Conversation/Message
models and a proper checkpointer exist.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user
from backend.db.models import Customer
from backend.agents.graph.graph_builder import build_graph
from backend.agents.graph.state import new_agent_state

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)

# conversation_id -> list[BaseMessage]. In-memory stand-in, see module docstring.
_conversations: dict[str, list] = {}


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
    _conversations[conversation_id] = []
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

    history = _conversations[conversation_id]

    compiled_graph = build_graph(db, current_user)
    initial_state = new_agent_state(customer_id=str(current_user.id), conversation_id=conversation_id)
    initial_state["messages"] = history + [HumanMessage(content=payload.message)]

    final_state = compiled_graph.invoke(initial_state)

    # Persist the updated history back into the in-memory store for the next turn.
    _conversations[conversation_id] = final_state["messages"]

    return {
        "conversation_id": conversation_id,
        "answer": final_state["messages"][-1].content,
        "intent": final_state.get("intent"),
    }