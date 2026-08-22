from pydantic import BaseModel, Field
from enum import Enum

class Intent(str, Enum):
    POLICY_QUESTION = "policy_question"      # general policy/FAQ -> RAG only
    ORDER_STATUS = "order_status"             # "where is my order" -> tools
    RETURN_REQUEST = "return_request"          # "I want to return X" -> tools
    REFUND_REQUEST = "refund_request"          # "where's my refund" -> tools
    CANCELLATION = "cancellation"              # "cancel my order" -> tools
    SUPPORT_OTHER = "support_other"            # ambiguous / needs a human ticket


class IntentClassification(BaseModel):
    intent: Intent = Field(description="The single best-fitting category for this message")
    confidence: float = Field(description="Confidence in this classification, from 0.0 to 1.0")
    reasoning: str = Field(description="One short sentence explaining why this category fits")