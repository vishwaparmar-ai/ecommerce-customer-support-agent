"""
Knowledge base ingestion for the ShopFlow AI RAG pipeline (LangChain version).

Reads the policy markdown files, splits each into section-level chunks
using LangChain's MarkdownHeaderTextSplitter, embeds them with a local
HuggingFace embedding model, and loads them into a persistent Chroma
vectorstore via LangChain's Chroma integration.

Install:
    pip install langchain langchain-text-splitters langchain-huggingface \
                langchain-chroma python-frontmatter sentence-transformers

Run from the project root:
    uv run python -m backend.rag.ingest

Re-running this script is safe: it wipes and rebuilds the collection each
time, so it's idempotent as your policy docs change.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter  # pip install python-frontmatter
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

import logging

logger = logging.getLogger(__name__)


POLICY_DOCS_DIR = Path(__file__).resolve().parent / "policy_docs"

CHROMA_PERSIST_DIR = str(Path(__file__).resolve().parent / "chroma_db")
COLLECTION_NAME = "shopflow_policies"


EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Split on H2 ("##") headers -- matches the section structure of every
# policy doc. LangChain strips the header line from page_content and puts
# it in metadata under the key given here ("section").
HEADERS_TO_SPLIT_ON = [("##", "section")]


# Loading + splitting

def load_policy_documents(docs_dir: Path = POLICY_DOCS_DIR) -> list[frontmatter.Post]:
    """Reads every .md file in docs_dir and parses its frontmatter + body."""
    if not docs_dir.exists():
        raise FileNotFoundError(
            f"Policy docs directory not found: {docs_dir}. "
            "Place your policy .md files there or update POLICY_DOCS_DIR."
        )

    posts = []
    for path in sorted(docs_dir.glob("*.md")):
        with open(path, "r", encoding="utf-8") as f:
            posts.append(frontmatter.load(f))
    return posts


def split_document(post: frontmatter.Post) -> list[Document]:
    """
    Splits one document's body into section-level LangChain Documents using
    MarkdownHeaderTextSplitter, then attaches the document's own frontmatter
    metadata (document_id, document_type, title, version, effective_date) to
    every resulting chunk alongside the section title LangChain extracts.
    """
    doc_metadata = post.metadata
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS_TO_SPLIT_ON, strip_headers=False)
    section_docs = splitter.split_text(post.content)

    chunks: list[Document] = []
    for i, section_doc in enumerate(section_docs):
        merged_metadata = {
            "document_id": doc_metadata["document_id"],
            "document_type": doc_metadata["document_type"],
            "title": doc_metadata["title"],
            "version": str(doc_metadata["version"]),
            "effective_date": str(doc_metadata["effective_date"]),
            "section": section_doc.metadata.get("section", doc_metadata["title"]),
            "chunk_id": f"{doc_metadata['document_id']}_{i}",
        }
        chunks.append(Document(page_content=section_doc.page_content, metadata=merged_metadata))

    return chunks


def split_all_documents(docs_dir: Path = POLICY_DOCS_DIR) -> list[Document]:
    posts = load_policy_documents(docs_dir)
    all_chunks: list[Document] = []
    for post in posts:
        all_chunks.extend(split_document(post))
    return all_chunks


# Embedding + vectorstore

def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        encode_kwargs={"normalize_embeddings": True},
    )


def ingest(docs_dir: Path = POLICY_DOCS_DIR) -> Chroma:
    logger.info("ingestion_started", extra={"docs_dir": str(docs_dir)})

    chunks = split_all_documents(docs_dir)
    logger.info("chunks_parsed", extra={"chunk_count": len(chunks)})

    logger.info("loading_embedding_model", extra={"model": EMBEDDING_MODEL_NAME})
    embeddings = get_embeddings()

    logger.info("embedding_and_writing_to_chroma", extra={"collection": COLLECTION_NAME})
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PERSIST_DIR,
    )

    # Wipe any existing chunks so re-running this script doesn't append
    # duplicates on top of stale ones.
    existing_ids = vectorstore.get()["ids"]
    if existing_ids:
        logger.info("clearing_existing_chunks", extra={"existing_count": len(existing_ids)})
        vectorstore.delete(ids=existing_ids)

    vectorstore.add_documents(
        documents=chunks,
        ids=[c.metadata["chunk_id"] for c in chunks],
    )

    logger.info(
        "ingestion_completed",
        extra={"chunk_count": len(chunks), "collection": COLLECTION_NAME},
    )
    return vectorstore


if __name__ == "__main__":
    ingest()