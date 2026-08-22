from pydantic import BaseModel

class PolicyAnswer(BaseModel):
    answer: str
    sources: list[dict]
    grounded: bool  # False if no relevant chunks were found at all