"""
Agent tools: orders.

Wraps read access to a customer's order as a typed LangChain tool.

Critical design point (per the project's security requirements): the LLM
must NEVER be trusted to supply customer_id. The tool's input schema only
takes what the model should actually decide (which order), while the
customer's identity is bound via closure when the tool is constructed --
from the authenticated session, not from anything the model outputs.

This is why these are factory functions (make_get_order_tool(db, current_user))
rather than plain @tool-decorated functions: each tool instance is created
fresh per-conversation, already scoped to one authenticated customer.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session

from backend.db.models import Customer
from backend.services.order_service import get_order_for_customer
from backend.schemas.order_tools import GetOrderInput

def _serialize_order(order) -> dict:
    """Converts an Order ORM object into a plain, JSON-safe dict for the LLM."""
    return {
        "order_id": str(order.id),
        "status": order.status.value,
        "total_amount": str(order.total_amount),
        "shipping_address": order.shipping_address,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "product_name": item.product.name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "subtotal": str(item.subtotal),
            }
            for item in order.items
        ],
        "payment_status": order.payment.status.value if order.payment else None,
        "shipment_status": order.shipment.status.value if order.shipment else None,
    }


def make_get_order_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a get_order tool scoped to current_user. The model can only pass
    order_id -- ownership is enforced inside get_order_for_customer using
    current_user.id, which is captured here from the authenticated session,
    never from model input.
    """

    def _get_order(order_id: uuid.UUID) -> dict:
        try:
            order = get_order_for_customer(db, order_id, current_user.id)
            result = _serialize_order(order)
          
            return result
        except Exception as exc:
            # Tools shouldn't raise HTTP-specific exceptions -- the agent
            # needs a plain error signal it can reason about or escalate on.
         
            return {"error": str(getattr(exc, "detail", exc))}

    return StructuredTool.from_function(
        func=_get_order,
        name="get_order",
        description=(
            "Look up the current customer's own order by its order_id. "
            "Returns order status, total amount, items, payment status, "
            "and shipment status. Only works for orders the customer owns."
        ),
        args_schema=GetOrderInput,
    )


# ---------------------------------------------------------------------------
# Manual test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    """
    Quick manual check: pulls a real customer + one of their orders from
    the seeded DB, builds the tool, and calls it both correctly and with
    someone else's order to confirm ownership enforcement works.
    """
    from backend.db.session import SessionLocal
    from backend.db.models import Order

    db = SessionLocal()
    try:
        # Query from Order first to guarantee we land on a customer who
        # actually has at least one order (seed data gives each customer
        # 0-5 orders randomly, so Customer.first() might have none).
        own_order = db.query(Order).first()
        if own_order is None:
            raise RuntimeError("No orders found in the database -- run the seed script first.")
        customer = db.query(Customer).filter(Customer.id == own_order.customer_id).first()
        other_order = db.query(Order).filter(Order.customer_id != customer.id).first()

        tool = make_get_order_tool(db, customer)

        print("Own order lookup:")
        print(tool.invoke({"order_id": str(own_order.id)}))

        print("\nSomeone else's order (should error):")
        print(tool.invoke({"order_id": str(other_order.id)}))
    finally:
        db.close()