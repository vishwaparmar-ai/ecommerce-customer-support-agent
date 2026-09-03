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
    get_cancellable_orders,
    get_order_for_customer,
)


class OrderSelection(BaseModel):

    order_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The order UUID explicitly mentioned by the customer, "
            "if present."
        ),
    )

    product_name: str | None = Field(
        default=None,
        description=(
            "The product/item name the customer uses to identify "
            "the order."
        ),
    )


def _get_latest_human_message(state: AgentState) -> str:

    for message in reversed(state["messages"]):

        if isinstance(message, HumanMessage):
            return message.content

    raise ValueError(
        "No customer message found."
    )


def _parse_confirmation(value) -> bool:

    if isinstance(value, bool):
        return value

    if isinstance(value, str):

        normalized = value.strip().lower()

        return normalized in {
            "yes",
            "y",
            "confirm",
            "confirmed",
            "true",
            "i confirm",
            "yes, i confirm this action.",
        }

    return False


def _get_product_names(order) -> list[str]:

    return [
        item.product.name
        for item in order.items
        if item.product is not None
    ]


def _format_order(order) -> str:

    product_names = _get_product_names(order)

    products = (
        ", ".join(product_names)
        if product_names
        else "Unknown item"
    )

    return (
        f"Order {order.id} — "
        f"{products} — "
        f"₹{order.total_amount} — "
        f"{order.status.value}"
    )


def _find_order_by_product_name(
    orders,
    product_name: str,
):

    query = product_name.strip().lower()

    matches = []

    for order in orders:

        for item in order.items:

            if item.product is None:
                continue

            product_name_db = item.product.name.lower()

            if (
                query in product_name_db
                or product_name_db in query
            ):
                matches.append(order)
                break

    return matches


def make_cancellation_node(
    db: Session,
    current_user: Customer,
):

    extractor_llm = (
        ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0,
        )
        .with_structured_output(OrderSelection)
    )

    def cancellation_node(
        state: AgentState,
    ) -> dict:

        # =========================================================
        # RESUME PATH
        # =========================================================
        #
        # If pending_order_id exists, the graph is resuming an
        # already-created cancellation request.
        #
        # DO NOT run order identification again.
        #
        # =========================================================

        pending_order_id = state.get(
            "pending_order_id"
        )

        if pending_order_id:

            logger.info(
                "cancellation_resume",
                extra={
                    "customer_id": str(current_user.id),
                    "order_id": pending_order_id,
                },
            )

            order = get_order_for_customer(
                db=db,
                order_id=uuid.UUID(pending_order_id),
                customer_id=current_user.id,
            )

            # -----------------------------------------------------
            # The interrupt returns the value supplied through
            # Command(resume=...).
            # -----------------------------------------------------

            confirmation = interrupt(
                {
                    "action": "cancel_order",
                    "order_id": str(order.id),
                    "total_amount": str(order.total_amount),
                    "question": (
                        f"You're cancelling "
                        f"{', '.join(_get_product_names(order))} "
                        f"(order {order.id}) for "
                        f"₹{order.total_amount}. "
                        f"This cannot be undone. "
                        f"Would you like me to cancel it?"
                    ),
                }
            )

            confirmed = _parse_confirmation(
                confirmation
            )

            logger.info(
                "cancellation_confirmation_received",
                extra={
                    "customer_id": str(current_user.id),
                    "order_id": str(order.id),
                    "confirmed": confirmed,
                    "confirmation_value": str(
                        confirmation
                    ),
                },
            )

            # -----------------------------------------------------
            # Customer rejected
            # -----------------------------------------------------

            if not confirmed:

                return {
                    "messages": [
                        AIMessage(
                            content=(
                                "Okay, I won't cancel the order."
                            )
                        )
                    ],
                    "requires_approval": False,
                    "approved": False,
                    "pending_order_id": None,
                }

            # -----------------------------------------------------
            # Customer confirmed
            # -----------------------------------------------------

            try:

                cancel_order_service(
                    db,
                    current_user,
                    order.id,
                )

                logger.info(
                    "order_cancelled",
                    extra={
                        "customer_id": str(
                            current_user.id
                        ),
                        "order_id": str(order.id),
                    },
                )

                return {
                    "messages": [
                        AIMessage(
                            content=(
                                f"Your order {order.id} "
                                "has been cancelled successfully."
                            )
                        )
                    ],
                    "requires_approval": True,
                    "approved": True,
                    "pending_order_id": None,
                }

            except Exception:

                logger.exception(
                    "order_cancellation_failed",
                    extra={
                        "customer_id": str(
                            current_user.id
                        ),
                        "order_id": str(order.id),
                    },
                )

                return {
                    "messages": [
                        AIMessage(
                            content=(
                                "I couldn't cancel the order. "
                                "I'm connecting you with support."
                            )
                        )
                    ],
                    "escalated": True,
                    "pending_order_id": None,
                }

        # =========================================================
        # FIRST RUN
        # =========================================================

        question = _get_latest_human_message(
            state
        )

        # ---------------------------------------------------------
        # Get ONLY this customer's cancellable orders.
        # ---------------------------------------------------------

        cancellable_orders = get_cancellable_orders(
            db=db,
            customer_id=current_user.id,
        )

        if not cancellable_orders:

            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I couldn't find any orders "
                            "that can currently be cancelled."
                        )
                    )
                ]
            }

        # ---------------------------------------------------------
        # Understand what the customer means.
        # ---------------------------------------------------------

        try:

            extraction: OrderSelection = (
                extractor_llm.invoke(
                    (
                        "Identify which order the customer "
                        "wants to cancel.\n\n"
                        "If they explicitly provide an order "
                        "ID, extract it.\n\n"
                        "Otherwise identify the product/item "
                        "name they refer to.\n\n"
                        f"Customer message:\n{question}"
                    )
                )
            )

        except Exception:

            logger.exception(
                "order_selection_failed",
                extra={
                    "customer_id": str(
                        current_user.id
                    )
                },
            )

            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I couldn't determine which order "
                            "you want to cancel. Please tell "
                            "me the product name."
                        )
                    )
                ]
            }

        selected_order = None

        # ---------------------------------------------------------
        # Explicit order ID
        # ---------------------------------------------------------

        if extraction.order_id:

            selected_order = get_order_for_customer(
                db=db,
                order_id=extraction.order_id,
                customer_id=current_user.id,
            )

        # ---------------------------------------------------------
        # Product-based selection
        # ---------------------------------------------------------

        elif extraction.product_name:

            matches = _find_order_by_product_name(
                cancellable_orders,
                extraction.product_name,
            )

            if len(matches) == 1:

                selected_order = matches[0]

            elif len(matches) > 1:

                order_list = "\n".join(
                    f"{index}. {_format_order(order)}"
                    for index, order in enumerate(
                        matches,
                        start=1,
                    )
                )

                return {
                    "messages": [
                        AIMessage(
                            content=(
                                "I found multiple matching "
                                "orders:\n\n"
                                f"{order_list}\n\n"
                                "Which one would you like "
                                "to cancel?"
                            )
                        )
                    ]
                }

        # ---------------------------------------------------------
        # If there is exactly one cancellable order,
        # identify it automatically.
        # ---------------------------------------------------------

        if selected_order is None:

            if len(cancellable_orders) == 1:

                selected_order = cancellable_orders[0]

            else:

                order_list = "\n".join(
                    f"{index}. {_format_order(order)}"
                    for index, order in enumerate(
                        cancellable_orders,
                        start=1,
                    )
                )

                return {
                    "messages": [
                        AIMessage(
                            content=(
                                "I found these orders that "
                                "can currently be cancelled:\n\n"
                                f"{order_list}\n\n"
                                "Which one would you like "
                                "to cancel?"
                            )
                        )
                    ]
                }

        # ---------------------------------------------------------
        # Eligibility check
        # ---------------------------------------------------------

        if (
            selected_order.status
            not in CANCELLABLE_STATES
        ):

            return {
                "messages": [
                    AIMessage(
                        content=(
                            "This order can no longer "
                            "be cancelled."
                        )
                    )
                ]
            }

        # =========================================================
        # SAVE THE ORDER BEFORE INTERRUPTING
        # =========================================================

        # This is the key fix.
        #
        # LangGraph will checkpoint this state before pausing.
        #
        # When the user confirms, we retrieve this exact order
        # instead of trying to identify it again.
        # =========================================================

        pending_order_id = str(
            selected_order.id
        )

        will_refund = (
            selected_order.payment is not None
            and selected_order.payment.status.value
            == "paid"
        )

        # ---------------------------------------------------------
        # Pause for explicit confirmation
        # ---------------------------------------------------------

        confirmation = interrupt(
            {
                "action": "cancel_order",
                "order_id": pending_order_id,
                "total_amount": str(
                    selected_order.total_amount
                ),
                "will_refund": will_refund,
                "question": (
                    f"You're cancelling "
                    f"{', '.join(_get_product_names(selected_order))} "
                    f"(order {selected_order.id}) "
                    f"for ₹{selected_order.total_amount}. "
                    f"This cannot be undone. "
                    f"Would you like me to cancel it?"
                ),
            }
        )

        confirmed = _parse_confirmation(
            confirmation
        )

        # ---------------------------------------------------------
        # Declined
        # ---------------------------------------------------------

        if not confirmed:

            return {
                "messages": [
                    AIMessage(
                        content=(
                            "Okay, I won't cancel the order."
                        )
                    )
                ],
                "requires_approval": False,
                "approved": False,
                "pending_order_id": None,
            }

        # ---------------------------------------------------------
        # Confirmed
        # ---------------------------------------------------------

        try:

            cancel_order_service(
                db,
                current_user,
                selected_order.id,
            )

            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"Your order "
                            f"{selected_order.id} "
                            "has been cancelled successfully."
                            + (
                                " A refund will be processed."
                                if will_refund
                                else ""
                            )
                        )
                    )
                ],
                "requires_approval": True,
                "approved": True,
                "pending_order_id": None,
            }

        except Exception:

            logger.exception(
                "order_cancellation_failed",
                extra={
                    "customer_id": str(
                        current_user.id
                    ),
                    "order_id": str(
                        selected_order.id
                    ),
                },
            )

            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I couldn't cancel the order. "
                            "I'm connecting you with support."
                        )
                    )
                ],
                "escalated": True,
                "pending_order_id": None,
            }

    return cancellation_node