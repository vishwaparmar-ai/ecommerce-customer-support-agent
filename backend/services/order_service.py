"""
1. Create order
2. Cancel order
"""

from __future__ import annotations
from backend.schemas.orders import OrderItem,OrderCreate
from backend.db.models import Order
from fastapi import HTTPException,status
from sqlalchemy.orm import Session
from uuid import UUID

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session


from backend.db.models import (
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
)

# States from which an order can still be cancelled by the customer.
CANCELLABLE_STATES = {
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
}




# ---------------------------------------------------------------------------
# Shared lookup
# ---------------------------------------------------------------------------
def get_order_for_customer(db: Session, order_id: uuid.UUID, customer_id: uuid.UUID) -> Order:
    """Fetch an order and enforce ownership. Raises 404 if missing, 403 if not owned."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this order")
    return order


# ---------------------------------------------------------------------------
# Create order
# ---------------------------------------------------------------------------
def create_order(db: Session, current_user: Customer, data: OrderCreate) -> Order:
    """
    Validates products/stock, computes totals from DB prices (never trusts
    client-sent prices), reserves stock, and creates the Order, OrderItems,
    and Payment as a single transaction. Rolls back entirely on any failure.
    """
    if not data.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order must contain at least one item")

    try:
        order = Order(
            id=uuid.uuid4(),
            customer_id=current_user.id,
            status=OrderStatus.PENDING,
            total_amount=Decimal("0.00"),
            shipping_address=data.shipping_address,
        )
        db.add(order)
        db.flush()  # assigns order.id without committing

        total = Decimal("0.00")

        for item in data.items:
            if item.quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Item quantity must be greater than zero",
                )

            # Row-lock the product so two concurrent orders can't
            # oversell the same remaining stock.
            product = (
                db.query(Product)
                .filter(Product.id == item.product_id)
                .with_for_update()
                .first()
            )

            if product is None or not product.is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product {item.product_id} is not available",
                )

            if product.stock_quantity < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for '{product.name}' "
                           f"(requested {item.quantity}, available {product.stock_quantity})",
                )

            # Reserve stock and price using the DB value, not client input.
            product.stock_quantity -= item.quantity
            unit_price = product.price
            subtotal = unit_price * item.quantity
            total += subtotal

            db.add(OrderItem(
                id=uuid.uuid4(),
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                unit_price=unit_price,
                subtotal=subtotal,
            ))

        order.total_amount = total
        order.status = OrderStatus.CONFIRMED

        db.add(Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            amount=total,
            method=data.payment_method,
            status=PaymentStatus.PENDING,
        ))

        db.commit()
        db.refresh(order)

      
        return order

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order",
        )


# ---------------------------------------------------------------------------
# Cancel order
# ---------------------------------------------------------------------------
def cancel_order(db: Session, current_user: Customer, order_id: uuid.UUID) -> Order:
    """
    Validates ownership and current state, restocks items, and cancels
    the order. Only allowed while the order is still in a pre-fulfillment
    state (see CANCELLABLE_STATES).
    """
    order = get_order_for_customer(db, order_id, current_user.id)

    if order.status not in CANCELLABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order cannot be cancelled from status '{order.status.value}'",
        )

    try:
        # Restock each item.
        for item in order.items:
            product = (
                db.query(Product)
                .filter(Product.id == item.product_id)
                .with_for_update()
                .first()
            )
            if product is not None:
                product.stock_quantity += item.quantity

        order.status = OrderStatus.CANCELLED

        if order.payment and order.payment.status == PaymentStatus.PAID:
            # Money was already collected -- this should trigger a real
            # refund flow rather than silently flipping the flag. Marking
            # here as a placeholder; wire this to refund_service once that
            # exists.
            order.payment.status = PaymentStatus.REFUNDED

        db.commit()
        db.refresh(order)

        
        return order

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel order",
        )

def get_cancellable_orders(
    db: Session,
    customer_id: uuid.UUID,
) -> list[Order]:
    """
    Return all orders belonging to the authenticated customer that are
    currently eligible for cancellation.

    This function is intentionally scoped by customer_id so the agent
    can never see another customer's orders.
    """
    return (
        db.query(Order)
        .filter(
            Order.customer_id == customer_id,
            Order.status.in_(CANCELLABLE_STATES),
        )
        .order_by(Order.created_at.desc())
        .all()
    )