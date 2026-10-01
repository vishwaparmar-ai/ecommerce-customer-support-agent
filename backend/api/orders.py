from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user
from backend.db.models import Customer
from backend.schemas.orders import (
    OrderCreate,
    OrderDetailResponse,
    OrderItemResponse,
    OrderSummaryResponse,
    PaymentResponse,
    ShipmentResponse,
)
from backend.services.order_service import (
    cancel_order,
    create_order,
    get_order_for_customer,
    get_order_payment,
    get_order_shipment,
    list_orders_for_customer,
)

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
)
def create_new_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Create a new order for the authenticated customer."""
    order = create_order(
        db=db,
        current_user=current_user,
        data=data,
    )

    return {
        "message": "Order created successfully",
        "order_id": order.id,
        "status": order.status.value,
        "total_amount": str(order.total_amount),
    }


@router.get("/", response_model=list[OrderSummaryResponse])
def list_my_orders(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """List all orders belonging to the authenticated customer."""
    orders = list_orders_for_customer(
        db=db,
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [
        OrderSummaryResponse(
            id=o.id,
            customer_id=o.customer_id,
            status=o.status,
            total_amount=o.total_amount,
            shipping_address=o.shipping_address,
            created_at=o.created_at,
            item_count=len(o.items),
        )
        for o in orders
    ]


@router.get("/{order_id}", response_model=OrderDetailResponse)
def get_order_details(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Get complete details for an order owned by the authenticated customer."""
    order = get_order_for_customer(db=db, order_id=order_id, customer_id=current_user.id)

    items = [
        OrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product.name if item.product else None,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,
        )
        for item in order.items
    ]

    payment = None
    if order.payment:
        payment = PaymentResponse(
            id=order.payment.id,
            order_id=order.payment.order_id,
            amount=order.payment.amount,
            method=order.payment.method,
            status=order.payment.status,
            transaction_reference=order.payment.transaction_reference,
            created_at=order.payment.created_at,
        )

    shipment = None
    if order.shipment:
        shipment = ShipmentResponse(
            id=order.shipment.id,
            order_id=order.shipment.order_id,
            carrier=order.shipment.carrier,
            tracking_number=order.shipment.tracking_number,
            status=order.shipment.status,
            estimated_delivery=order.shipment.estimated_delivery,
            actual_delivery=order.shipment.actual_delivery,
        )

    return OrderDetailResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total_amount=order.total_amount,
        shipping_address=order.shipping_address,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items,
        payment=payment,
        shipment=shipment,
    )


@router.post(
    "/{order_id}/cancel",
    status_code=status.HTTP_200_OK,
)
def cancel_existing_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Cancel an eligible order belonging to the authenticated customer."""
    order = cancel_order(
        db=db,
        current_user=current_user,
        order_id=order_id,
    )

    return {
        "message": "Order cancelled successfully",
        "order_id": order.id,
        "status": order.status.value,
    }


@router.get("/{order_id}/payment", response_model=PaymentResponse)
def get_order_payment_status(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Inspect payment details and status for an owned order."""
    payment = get_order_payment(db=db, order_id=order_id, customer_id=current_user.id)
    return PaymentResponse(
        id=payment.id,
        order_id=payment.order_id,
        amount=payment.amount,
        method=payment.method,
        status=payment.status,
        transaction_reference=payment.transaction_reference,
        created_at=payment.created_at,
    )


@router.get("/{order_id}/shipment", response_model=ShipmentResponse)
def get_order_shipment_status(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Track shipment status and delivery details for an owned order."""
    shipment = get_order_shipment(db=db, order_id=order_id, customer_id=current_user.id)
    return ShipmentResponse(
        id=shipment.id,
        order_id=shipment.order_id,
        carrier=shipment.carrier,
        tracking_number=shipment.tracking_number,
        status=shipment.status,
        estimated_delivery=shipment.estimated_delivery,
        actual_delivery=shipment.actual_delivery,
    )