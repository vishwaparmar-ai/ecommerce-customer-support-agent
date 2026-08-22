"""
Retrieval for the ShopFlow AI RAG pipeline.

Wraps the Chroma vectorstore built by ingest.py as a LangChain retriever,
so it can be used directly inside a chain, or plugged into a LangGraph
node/tool later.

Reuses the same embedding model, persist directory, and collection name
as ingest.py so retrieval queries the exact same vector space it was
built with.
"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

import logging
from backend.rag.ingestion import (
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    get_embeddings,
)


logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 4


# ---------------------------------------------------------------------------
# Vectorstore + retriever
# ---------------------------------------------------------------------------
def get_vectorstore() -> Chroma:
    """
    Opens the existing persisted Chroma collection (does not re-ingest --
    run `python -m backend.rag.ingest` first if the collection is empty).
    """
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=CHROMA_PERSIST_DIR,
    )


def get_retriever(k: int = DEFAULT_TOP_K) -> VectorStoreRetriever:
    """
    Returns a LangChain retriever over the policy knowledge base, ready to
    drop into a chain (`retriever | ...`) or a LangGraph node.
    """
    vectorstore = get_vectorstore()
    return vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": k})


# Convenience function for direct use (e.g. from a tool or a quick script)

def retrieve_policy_chunks(query: str, k: int = DEFAULT_TOP_K) -> list[dict]:
    """
    Runs a similarity search for `query` and returns the top-k chunks as
    plain dicts (content + metadata)
    """
    retriever = get_retriever(k=k)
    results: list[Document] = retriever.invoke(query)

    logger.info(
        "policy_retrieval",
        extra={"query": query, "result_count": len(results)},
    )

    return [
        {
            "content": doc.page_content,
            "document_id": doc.metadata.get("document_id"),
            "document_type": doc.metadata.get("document_type"),
            "title": doc.metadata.get("title"),
            "section": doc.metadata.get("section"),
            "version": doc.metadata.get("version"),
            "effective_date": doc.metadata.get("effective_date"),
        }
        for doc in results
    ]


# # ---------------------------------------------------------------------------
# # Manual test
# # ---------------------------------------------------------------------------
# if __name__ == "__main__":
#     test_query = "What is the return window for electronics?"
#     chunks = retrieve_policy_chunks(test_query)

#     print(f"\nQuery: {test_query}\n")
#     for i, chunk in enumerate(chunks, start=1):
#         print(f"--- Result {i} ({chunk['document_type']} / {chunk['section']}) ---")
#         print(chunk["content"])
#         print()