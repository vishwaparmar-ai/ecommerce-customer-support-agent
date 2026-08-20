from pydantic import BaseModel
from uuid import UUID
from db.models import PaymentMethod

class OrderItem(BaseModel):
    product_id:UUID
    quantity:int

class OrderCreate(BaseModel):
    items:list[OrderItem]
    shipping_address: str
    payment_method: PaymentMethod
