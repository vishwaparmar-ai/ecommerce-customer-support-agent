from pydantic import BaseModel

class CustomerQuery(BaseModel):
    query:str

class CustomerResponse(BaseModel):
    response:str