from pydantic import BaseModel,EmailStr
from uuid import UUID

class CustomerCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone:int

class CustomerLogin(BaseModel):
    email: EmailStr
    password:str

class CustomerResponse(BaseModel):
    id: UUID
    name: str
    email: EmailStr

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str

class QueryRequest(BaseModel):
    dataset_id:int
    question:str