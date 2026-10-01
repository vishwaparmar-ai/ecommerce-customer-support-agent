from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field

from backend.db.models import OrderStatus, PaymentMethod, PaymentStatus, ShipmentStatus


class OrderItem(BaseModel):
    product_id: UUID
    quantity: int = Field(..., gt=0)


class OrderCreate(BaseModel):
    items: list[OrderItem]
    shipping_address: str = Field(..., min_length=1)
    payment_method: PaymentMethod = PaymentMethod.CARD


class OrderItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str | None = None
    quantity: int
    unit_price: Decimal
    subtotal: Decimal

    class Config:
        from_attributes = True


class PaymentResponse(BaseModel):
    id: UUID
    order_id: UUID
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    transaction_reference: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ShipmentResponse(BaseModel):
    id: UUID
    order_id: UUID
    carrier: str
    tracking_number: str
    status: ShipmentStatus
    estimated_delivery: datetime | None = None
    actual_delivery: datetime | None = None

    class Config:
        from_attributes = True


class OrderSummaryResponse(BaseModel):
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total_amount: Decimal
    shipping_address: str
    created_at: datetime
    item_count: int

    class Config:
        from_attributes = True


class OrderDetailResponse(BaseModel):
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total_amount: Decimal
    shipping_address: str
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse] = []
    payment: PaymentResponse | None = None
    shipment: ShipmentResponse | None = None

    class Config:
        from_attributes = True
