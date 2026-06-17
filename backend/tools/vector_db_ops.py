"""
Tools: vector_db_search and vector_db_store
Qdrant semantic search and document storage operations.
"""
from __future__ import annotations

from typing import Any, Optional

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.memory.long_term import LongTermMemory
from backend.tools.registry import registry

logger = get_logger(__name__)

_ltm = LongTermMemory()


@registry.register(
    name="vector_db_search",
    description=(
        "Search the vector database for semantically similar documents. "
        "Use this to retrieve previously stored research, financial facts, "
        "and documents relevant to the current query."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Semantic search query",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return",
                "default": 10,
            },
            "filter_type": {
                "type": "string",
                "description": "Filter by document type (e.g., 'sec_filing', 'news', 'analysis')",
                "default": "",
            },
            "filter_ticker": {
                "type": "string",
                "description": "Filter by company ticker",
                "default": "",
            },
        },
        "required": ["query"],
    },
    timeout=15.0,
)
@with_retry(service="qdrant")
async def vector_db_search(
    query: str,
    top_k: int = 10,
    filter_type: str = "",
    filter_ticker: str = "",
) -> dict[str, Any]:
    """Search vector database for semantically similar documents."""
    logger.info("vector_db_search", query=query[:80])

    filter_metadata: dict[str, Any] = {}
    if filter_type:
        filter_metadata["type"] = filter_type
    if filter_ticker:
        filter_metadata["ticker"] = filter_ticker.upper()

    results = await _ltm.search(
        query=query,
        top_k=top_k,
        filter_metadata=filter_metadata or None,
    )

    return {
        "query": query,
        "results": results,
        "total": len(results),
        "filter_applied": bool(filter_metadata),
        "source": "Qdrant Vector Database",
    }


@registry.register(
    name="vector_db_store",
    description=(
        "Store a document in the vector database for future retrieval. "
        "Use this to persist research findings, extracted facts, and "
        "processed financial data for semantic search."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text content to store",
            },
            "doc_type": {
                "type": "string",
                "description": "Type of document (e.g., 'sec_filing', 'news', 'analysis', 'earnings')",
            },
            "ticker": {
                "type": "string",
                "description": "Company ticker associated with this document",
                "default": "",
            },
            "source": {
                "type": "string",
                "description": "Source of the document (e.g., 'SEC EDGAR', 'Reuters')",
                "default": "",
            },
            "metadata": {
                "type": "object",
                "description": "Additional metadata to store with the document",
                "default": {},
            },
        },
        "required": ["text", "doc_type"],
    },
    timeout=15.0,
)
@with_retry(service="qdrant")
async def vector_db_store(
    text: str,
    doc_type: str,
    ticker: str = "",
    source: str = "",
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """Store a document in the vector database."""
    logger.info("vector_db_store", doc_type=doc_type, ticker=ticker)

    doc_metadata = {
        "type": doc_type,
        "ticker": ticker.upper() if ticker else "",
        "source": source,
        **(metadata or {}),
    }

    doc_id = await _ltm.store(text=text, metadata=doc_metadata)

    return {
        "success": True,
        "doc_id": doc_id,
        "doc_type": doc_type,
        "ticker": ticker,
        "text_length": len(text),
    }
