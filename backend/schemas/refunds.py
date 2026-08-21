from pydantic import BaseModel
from uuid import UUID

class OrderRefund(BaseModel):
    return_id:UUID