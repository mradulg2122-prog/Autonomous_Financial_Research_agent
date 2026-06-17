"""
ARA-1 Long-Term Memory — Qdrant Vector DB
Stores document embeddings using text-embedding-3-large.
Supports: store, search, delete, update.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from backend.core.config import settings
from backend.core.errors import EmbeddingError, VectorDBError
from backend.core.logging import get_logger

logger = get_logger(__name__)

_qdrant_client: Optional[AsyncQdrantClient] = None
_openai_client: Optional[AsyncOpenAI] = None


async def get_qdrant() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        # prefer_grpc=False forces HTTP/REST mode, avoiding Windows DLL policy issues
        # that block the gRPC native extension (cygrpc).
        _qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            prefer_grpc=False,
            api_key=settings.qdrant_api_key or None,
        )
    return _qdrant_client


def get_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        _openai_client = AsyncOpenAI(**kwargs)
    return _openai_client


async def ensure_collection() -> None:
    """Create the Qdrant collection if it does not exist."""
    client = await get_qdrant()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if settings.qdrant_collection_name not in names:
        await client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(
                size=settings.qdrant_vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(
            "qdrant_collection_created",
            collection=settings.qdrant_collection_name,
        )


async def embed_text(text: str) -> list[float]:
    """Generate an embedding using text-embedding-3-large."""
    try:
        client = get_openai()
        response = await client.embeddings.create(
            model=settings.openai_embedding_model,
            input=text,
        )
        return response.data[0].embedding
    except Exception as exc:
        raise EmbeddingError(f"Failed to generate embedding: {exc}", code="EMBEDDING_ERROR")


class LongTermMemory:
    """
    Qdrant-backed long-term memory.
    Stores: research documents, facts, summaries with metadata.
    """

    def __init__(self, collection: str = None):
        self.collection = collection or settings.qdrant_collection_name

    async def store(
        self,
        text: str,
        metadata: dict[str, Any],
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Embed and store a document.
        Returns the Qdrant point ID.
        """
        try:
            point_id = doc_id or str(uuid.uuid4())
            vector = await embed_text(text)
            client = await get_qdrant()
            await client.upsert(
                collection_name=self.collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "text": text,
                            **metadata,
                        },
                    )
                ],
            )
            logger.debug("vector_stored", id=point_id, collection=self.collection)
            return point_id
        except EmbeddingError:
            raise
        except Exception as exc:
            raise VectorDBError(f"Failed to store document: {exc}", code="QDRANT_STORE_ERROR")

    async def search(
        self,
        query: str,
        top_k: int = None,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search using query embedding.
        Returns ranked list of matching documents with scores.
        """
        try:
            k = top_k or settings.rag_top_k
            vector = await embed_text(query)
            client = await get_qdrant()

            qdrant_filter = None
            if filter_metadata:
                conditions = [
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filter_metadata.items()
                ]
                qdrant_filter = Filter(must=conditions)

            results = await client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=k,
                query_filter=qdrant_filter,
                with_payload=True,
            )
            return [
                {
                    "id": str(r.id),
                    "score": r.score,
                    "text": r.payload.get("text", ""),
                    "metadata": {k: v for k, v in r.payload.items() if k != "text"},
                }
                for r in results
            ]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise VectorDBError(f"Search failed: {exc}", code="QDRANT_SEARCH_ERROR")

    async def delete(self, doc_id: str) -> None:
        """Remove a document from the collection."""
        try:
            client = await get_qdrant()
            await client.delete(
                collection_name=self.collection,
                points_selector=[doc_id],
            )
        except Exception as exc:
            raise VectorDBError(f"Delete failed: {exc}", code="QDRANT_DELETE_ERROR")

    async def count(self) -> int:
        """Return the total number of points in the collection."""
        try:
            client = await get_qdrant()
            info = await client.get_collection(self.collection)
            return info.points_count or 0
        except Exception:
            return 0
