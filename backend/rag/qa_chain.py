"""
RAG Q&A chain for the ShopFlow AI support agent.

Takes a customer's policy question, retrieves relevant chunks from the
Chroma knowledge base (backend.rag.retriever), and generates a grounded
answer using an LLM -- constrained to only use the retrieved context, so
it can't invent policy details that aren't actually in the documents.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.core.config import settings
from backend.rag.retriever import retrieve_policy_chunks, DEFAULT_TOP_K
from backend.prompts.qa_prompt_v1 import SYSTEM_PROMPT
from backend.schemas.policy import PolicyAnswer


def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.2,  # a little natural phrasing, still mostly deterministic
    )


def _format_context(chunks: list[dict]) -> str:
    """Formats retrieved chunks into labeled context blocks for the prompt."""
    blocks = []
    for chunk in chunks:
        blocks.append(
            f"[{chunk['document_type']} - {chunk['section']}]\n{chunk['content']}"
        )
    return "\n\n".join(blocks)


def answer_policy_question(question: str, k: int = DEFAULT_TOP_K) -> PolicyAnswer:
    """
    Retrieves the top-k relevant policy chunks for `question` and generates
    a grounded answer from them. Returns the answer text plus the sources
    used, so the caller can cite them or log them for evaluation later.
    """
    chunks = retrieve_policy_chunks(question, k=k)

    if not chunks:
        return PolicyAnswer(
            answer="I don't have information about that in our policies. "
                   "I can connect you with a support agent if you'd like.",
            sources=[],
            grounded=False,
        )

    context = _format_context(chunks)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ])

    llm = _get_llm()
    chain = prompt | llm
    response = chain.invoke({"context": context, "question": question})

    sources = [
        {
            "document_type": c["document_type"],
            "title": c["title"],
            "section": c["section"],
        }
        for c in chunks
    ]

    return PolicyAnswer(answer=response.text, sources=sources, grounded=True)


# ---------------------------------------------------------------------------
# Manual test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_questions = [
        "What's your return window for electronics?",
        "Can I return groceries?",
        "How long does a refund take?",
        "Do you offer same-day delivery?",  # not covered anywhere -> should say so
    ]

    for q in test_questions:
        result = answer_policy_question(q)
        print(f"\nQuestion: {q}")
        print(f"Answer: {result.answer}")
        print(f"Grounded: {result.grounded}")
        if result.sources:
            print(f"Sources: {[s['section'] for s in result.sources]}")