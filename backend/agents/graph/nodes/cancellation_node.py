"""
Graph node: cancellation_node.

Destination for the "cancellation" route (cancellation intent). Unlike
every other node, this one is NOT a tool-calling loop -- it calls
order_service functions directly and uses LangGraph's real interrupt()
to pause for approval, replacing the standalone cancel_order tool's
`confirmed` flag hack with a structural pause enforced by the graph
runtime itself, not a prompt instruction the model could ignore.

How interrupt() actually behaves here (this matters for reading the code
correctly): when interrupt() is called, LangGraph raises an internal
exception that unwinds back to whoever called .invoke() -- the graph
pauses, saves state via the checkpointer, and returns control with the
payload passed to interrupt(). When resumed via Command(resume=value),
LangGraph RE-RUNS THIS ENTIRE FUNCTION FROM THE TOP -- it does not jump
back into the middle. On that re-run, the interrupt() call doesn't pause
again; it immediately returns `value` (whatever was passed to
Command(resume=...)). This is why everything before interrupt() here is
read-only (order lookup, eligibility check, order_id extraction) -- it's
safe to redo. The actual write (cancel_order_service) only happens AFTER
interrupt() returns, i.e. only on the resume run, exactly once.
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import logger
from backend.db.models import Customer
from backend.agents.graph.state import AgentState
from backend.services.order_service import (
    CANCELLABLE_STATES,
    cancel_order as cancel_order_service,
    get_order_for_customer,
)


class OrderIdExtraction(BaseModel):
    order_id: uuid.UUID | None = Field(
        default=None,
        description="The order UUID mentioned by the customer, if any is present in the message",
    )


def _get_latest_human_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No HumanMessage found in state -- cancellation_node needs at least one.")


def _parse_confirmation(value) -> bool:
    """Interprets whatever came back via Command(resume=...) as yes/no."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("yes", "y", "confirm", "true", "confirmed")
    return bool(value)


def make_cancellation_node(db: Session, current_user: Customer):
    """
    Builds the cancellation_node function, scoped to current_user.
    Register with graph.add_node("cancellation_node",
    make_cancellation_node(db, current_user)).
    """
    extractor_llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0,
    ).with_structured_output(OrderIdExtraction)

    def _cancellation_node(state: AgentState) -> dict:
        question = _get_latest_human_message(state)

        # Read-only: safe to redo on resume.
        extraction = extractor_llm.invoke(f"Extract the order ID from this message, if present: {question}")
        order_id = extraction.order_id

        if order_id is None:
            return {
                "messages": [AIMessage(content="Which order would you like to cancel? Please share the order ID.")],
            }

        try:
            order = get_order_for_customer(db, order_id, current_user.id)
        except Exception as exc:
            return {"messages": [AIMessage(content=str(getattr(exc, "detail", exc)))]}

        if order.status not in CANCELLABLE_STATES:
            return {
                "messages": [
                    AIMessage(
                        content=f"This order can't be cancelled -- it's already '{order.status.value}'."
                    )
                ],
            }

        will_refund = order.payment is not None and order.payment.status.value == "paid"

        # PAUSE HERE. Everything above this line will run again on resume;
        # everything below only runs once, after the customer has confirmed.
        confirmation = interrupt(
            {
                "action": "cancel_order",
                "order_id": str(order.id),
                "total_amount": str(order.total_amount),
                "will_refund": will_refund,
                "question": (
                    f"Cancel order {order.id} (total {order.total_amount})? "
                    f"{'A refund will be issued. ' if will_refund else ''}"
                    f"This cannot be undone."
                ),
            }
        )

        confirmed = _parse_confirmation(confirmation)

        if not confirmed:
            logger.info(
                "graph_node_cancellation_declined",
                extra={"customer_id": state["customer_id"], "order_id": str(order_id)},
            )
            return {
                "messages": [AIMessage(content="Okay, I won't cancel this order.")],
                "requires_approval": False,
                "approved": False,
            }

        try:
            cancel_order_service(db, current_user, order.id)
            logger.info(
                "graph_node_cancellation_executed",
                extra={"customer_id": state["customer_id"], "order_id": str(order_id)},
            )
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "Your order has been cancelled."
                            + (" A refund will be processed." if will_refund else "")
                        )
                    )
                ],
                "requires_approval": True,
                "approved": True,
            }
        except Exception as exc:
            logger.info(
                "graph_node_cancellation_failed",
                extra={"customer_id": state["customer_id"], "order_id": str(order_id), "error": str(exc)},
            )
            return {
                "messages": [AIMessage(content="I couldn't cancel this order -- connecting you with support.")],
                "escalated": True,
            }

    return _cancellation_node