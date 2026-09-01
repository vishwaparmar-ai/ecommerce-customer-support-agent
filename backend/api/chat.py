from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user
from backend.db.models import Customer, ConversationStatus, MessageRole
from backend.agents.graph.graph_builder import build_graph
from backend.services.conversation_service import (
    create_conversation,
    get_conversation_for_customer,
    add_message,
    set_conversation_status,
    maybe_update_summary,
)

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


class CreateConversationRequest(BaseModel):
    channel: str = "web"


class SendMessageRequest(BaseModel):
    message: str


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_conversation_endpoint(
    payload: CreateConversationRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    conversation = create_conversation(db, current_user)
    return {"conversation_id": str(conversation.id), "status": conversation.status.value}


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    conversation = get_conversation_for_customer(db, current_user, conversation_id)

    # Persist the customer's message regardless of active/paused --
    # it's part of the real transcript either way.
    add_message(db, conversation, role=MessageRole.USER, content=payload.message)

    compiled_graph = build_graph(db, current_user)
    config = {"configurable": {"thread_id": str(conversation.id)}}

    if conversation.status == ConversationStatus.PAUSED:
        result = compiled_graph.invoke(Command(resume=payload.message), config=config)
    else:
        result = compiled_graph.invoke(
            {
                "customer_id": str(current_user.id),
                "conversation_id": str(conversation.id),
                "messages": [HumanMessage(content=payload.message)],
            },
            config=config,
        )

    if "__interrupt__" in result:
        interrupt_payload = result["__interrupt__"][0].value
        set_conversation_status(db, conversation, ConversationStatus.PAUSED)
        add_message(
            db,
            conversation,
            role=MessageRole.ASSISTANT,
            content=interrupt_payload.get("question", "Please confirm this action."),
            meta={"requires_confirmation": True, **interrupt_payload},
        )
        maybe_update_summary(db, conversation)

        return {
            "conversation_id": str(conversation.id),
            "requires_confirmation": True,
            "confirmation_request": interrupt_payload,
        }

    answer = result["messages"][-1].content
    set_conversation_status(db, conversation, ConversationStatus.ACTIVE)
    add_message(
        db,
        conversation,
        role=MessageRole.ASSISTANT,
        content=answer,
        meta={"intent": result.get("intent"), "tool_calls": result.get("tool_calls", [])},
    )
    maybe_update_summary(db, conversation)

    return {
        "conversation_id": str(conversation.id),
        "answer": answer,
        "intent": result.get("intent"),
    }