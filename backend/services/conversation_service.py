"""
Conversation service.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.core.config import settings
from backend.db.models import Conversation, ConversationStatus, Customer, Message, MessageRole
from langchain_google_genai import ChatGoogleGenerativeAI

MESSAGE_THRESHOLD = 20  # recompute summary once a conversation has at least this many messages


def create_conversation(db: Session, current_user: Customer) -> Conversation:
    conversation = Conversation(
        id=uuid.uuid4(),
        customer_id=current_user.id,
        status=ConversationStatus.ACTIVE,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation_for_customer(db: Session, current_user: Customer, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if conversation.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this conversation")
    return conversation


def add_message(
    db: Session,
    conversation: Conversation,
    role: MessageRole,
    content: str,
    meta: dict | None = None,
) -> Message:
    message = Message(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role=role,
        content=content,
        meta=meta,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def set_conversation_status(db: Session, conversation: Conversation, new_status: ConversationStatus) -> None:
    conversation.status = new_status
    db.commit()


def maybe_update_summary(db: Session, conversation: Conversation) -> None:
    """
    Recomputes conversation.summary from the full transcript once the
    conversation has grown past MESSAGE_THRESHOLD messages. Recomputes
    from scratch each time rather than incrementally extending a prior
    summary -- simpler, and cheap enough at this conversation length that
    it's not worth the complexity of incremental summarization here.
    """
    db.refresh(conversation)  # ensure conversation.messages reflects rows just added
    if len(conversation.messages) < MESSAGE_THRESHOLD:
        return

    transcript = "\n".join(f"{m.role.value}: {m.content}" for m in conversation.messages)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0,
    )
    prompt = (
        "Summarize this customer support conversation in 2-4 sentences. "
        "Capture any order IDs mentioned, the customer's issue(s), and "
        "how things were resolved or left off:\n\n" + transcript
    )
    summary = llm.invoke(prompt).content

    conversation.summary = summary if isinstance(summary, str) else str(summary)
    db.commit()

    logger.info(
        "conversation_summary_updated",
        extra={"conversation_id": str(conversation.id), "message_count": len(conversation.messages)},
    )