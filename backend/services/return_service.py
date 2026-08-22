"""
Return service.

Encapsulates return eligibility rules and return creation so routers stay
thin:
    - check_return_eligibility: validates delivery, return window, product
      eligibility, and duplicate returns. Raises HTTPException on the first
      rule that fails.
    - create_return: runs eligibility checks, then creates the Return row.

Reuses get_order_for_customer from order_service so ownership checks stay
consistent across services.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import logging
from backend.db.models import Customer, Order, OrderStatus, Return, ReturnStatus
from backend.services.order_service import get_order_for_customer

logger = logging.getLogger(__name__)

# Policy: how many days after actual delivery a return can still be requested.
RETURN_WINDOW_DAYS = 10

# Categories that can never be returned (perishables, hygiene items, etc.).
# Adjust to match your actual catalog rules.
NON_RETURNABLE_CATEGORIES = {"Grocery"}


# Eligibility check

def check_return_eligibility(db: Session, current_user: Customer, order_id: uuid.UUID) -> Order:
    """
    Validates, in order:
        1. Order exists and belongs to the current customer.
        2. Order has actually been delivered.
        3. Request falls within the return window.
        4. Every item in the order is in a returnable category.
        5. No return already exists for this order.

    Returns the Order if all checks pass, otherwise raises HTTPException.
    """
    order = get_order_for_customer(db, order_id, current_user.id)

    if order.status != OrderStatus.DELIVERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has not been delivered yet, so it is not eligible for return",
        )

    if order.shipment is None or order.shipment.actual_delivery is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No delivery record found for this order",
        )

    delivered_at = order.shipment.actual_delivery
    window_ends = delivered_at + timedelta(days=RETURN_WINDOW_DAYS)
    if datetime.now(timezone.utc) > window_ends:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Return window has expired ({RETURN_WINDOW_DAYS} days from delivery)",
        )

    non_returnable_items = [
        item.product.name for item in order.items
        if item.product.category in NON_RETURNABLE_CATEGORIES
    ]
    if non_returnable_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The following items are not eligible for return: {', '.join(non_returnable_items)}",
        )

    existing_return = db.query(Return).filter(Return.order_id == order.id).first()
    if existing_return is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A return has already been requested for this order",
        )

    return order


# Create return

def create_return(db: Session, current_user: Customer, order_id: uuid.UUID, reason: str) -> Return:
    """Runs eligibility checks, then creates the Return in REQUESTED state."""
    if not reason or not reason.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A return reason is required")

    order = check_return_eligibility(db, current_user, order_id)

    try:
        ret = Return(
            id=uuid.uuid4(),
            order_id=order.id,
            customer_id=current_user.id,
            reason=reason.strip(),
            status=ReturnStatus.REQUESTED,
        )
        db.add(ret)
        db.commit()
        db.refresh(ret)

        logger.info(
            "return_requested",
            extra={"return_id": str(ret.id), "order_id": str(order.id), "customer_id": str(current_user.id)},
        )
        return ret

    except Exception:
        db.rollback()
        logger.exception("return_creation_failed", extra={"order_id": str(order_id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create return request",
        )