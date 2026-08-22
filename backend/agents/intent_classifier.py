"""
Intent classification for the ShopFlow AI support agent.

Classifies an incoming customer message into a typed intent category using
an LLM's structured-output mode -- not free text, an actual Pydantic
object the rest of the pipeline can branch on.

This is Phase 3 in isolation: just the classification step, testable on
its own before it gets wired into the full LangGraph router (Phase 5).



"""

from __future__ import annotations



from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.schemas.intent_classification import IntentClassification
from backend.core.config import settings
import logging 
from backend.prompts.classifier_prompt_v1 import SYSTEM_PROMPT






def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0,
    )


def classify_intent(message: str) -> IntentClassification:
    """
    Classifies a single customer message into an Intent, using the LLM's
    structured-output mode so the result is a validated Pydantic object,
    not text that needs to be parsed.
    """
    llm = _get_llm().with_structured_output(IntentClassification)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{message}"),
    ])

    chain = prompt | llm
    result: IntentClassification = chain.invoke({"message": message})

    return result


