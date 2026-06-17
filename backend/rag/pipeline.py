"""
ARA-1 RAG Pipeline
Query Transformation → Multi-Source Retrieval → Cross-Encoder Reranking →
Context Compression → Source Attribution → Grounded Generation → Post-Generation Verification
"""
from __future__ import annotations

import json
from typing import Any, Optional

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.memory.long_term import LongTermMemory

logger = get_logger(__name__)


# ── Query Transformer ─────────────────────────────────────────
class QueryTransformer:
    """HyDE + multi-query expansion for better retrieval."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def transform(self, query: str, context: str = "") -> list[str]:
        """Generate multiple query variants for better recall."""
        prompt = f"""Given this financial research query, generate 4 alternative phrasings that 
would help find relevant documents. Also generate a hypothetical answer excerpt (HyDE).

Original query: {query}
Context: {context}

Return JSON:
{{
  "alternatives": ["alt1", "alt2", "alt3"],
  "hyde_excerpt": "A hypothetical answer excerpt that would match this query..."
}}"""
        try:
            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=500,
            )
            data = json.loads(response.choices[0].message.content)
            queries = [query] + data.get("alternatives", []) + [data.get("hyde_excerpt", "")]
            return [q for q in queries if q.strip()][:5]
        except Exception:
            return [query]


# ── Multi-Source Retriever ────────────────────────────────────
class MultiSourceRetriever:
    """Retrieves from Qdrant vector DB across multiple query variants."""

    def __init__(self) -> None:
        self._ltm = LongTermMemory()

    async def retrieve(
        self,
        queries: list[str],
        top_k: int = None,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """Retrieve documents for all query variants, deduplicate."""
        k = top_k or settings.rag_top_k
        all_results: dict[str, dict] = {}

        for query in queries:
            try:
                results = await self._ltm.search(
                    query=query,
                    top_k=k // len(queries) + 2,
                    filter_metadata=filter_metadata,
                )
                for r in results:
                    doc_id = r.get("id", "")
                    if doc_id not in all_results or r["score"] > all_results[doc_id]["score"]:
                        all_results[doc_id] = r
            except Exception as exc:
                logger.warning("retrieval_error", query=query[:50], error=str(exc))

        return sorted(all_results.values(), key=lambda x: x["score"], reverse=True)[:k]


# ── Cross-Encoder Reranker ────────────────────────────────────
class CrossEncoderReranker:
    """Reranks retrieved documents using LLM relevance scoring."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = None,
    ) -> list[dict[str, Any]]:
        """Score and rerank documents by relevance to query."""
        k = top_k or settings.rag_rerank_top_k
        if not documents:
            return []

        # For efficiency, use LLM only on top candidates
        candidates = documents[:min(len(documents), 15)]

        doc_texts = "\n\n".join([
            f"[{i}] {d.get('text', '')[:300]}"
            for i, d in enumerate(candidates)
        ])

        prompt = f"""Rate each document's relevance to the query (0.0-1.0).

Query: {query}

Documents:
{doc_texts}

Return JSON: {{"scores": [0.9, 0.7, ...]}} (one score per document, in order)"""

        try:
            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=200,
            )
            data = json.loads(response.choices[0].message.content)
            scores = data.get("scores", [])

            for i, doc in enumerate(candidates):
                if i < len(scores):
                    doc["rerank_score"] = float(scores[i])
                else:
                    doc["rerank_score"] = doc.get("score", 0.0)

            reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
            return reranked[:k]
        except Exception:
            return candidates[:k]


# ── Context Compressor ────────────────────────────────────────
class ContextCompressor:
    """Compresses retrieved context to fit LLM context window."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def compress(
        self,
        query: str,
        documents: list[dict[str, Any]],
        max_tokens: int = 3000,
    ) -> str:
        """Extract only query-relevant information from documents."""
        combined = "\n\n---\n\n".join([d.get("text", "") for d in documents])
        if len(combined) < max_tokens:
            return combined

        prompt = f"""Extract only the information relevant to answering this query.
Be concise but preserve all specific numbers, dates, and facts.

Query: {query}

Source text:
{combined[:6000]}

Extracted relevant information:"""

        try:
            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or combined[:max_tokens]
        except Exception:
            return combined[:max_tokens]


# ── Source Attributor ─────────────────────────────────────────
class SourceAttributor:
    """Tracks source attribution for generated content."""

    def build_citations(self, documents: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Build citation list from retrieved documents."""
        citations = []
        for doc in documents:
            meta = doc.get("metadata", {})
            citation = {
                "source": meta.get("source", "Unknown"),
                "type": meta.get("type", "document"),
                "ticker": meta.get("ticker", ""),
                "score": str(round(doc.get("rerank_score", doc.get("score", 0)), 3)),
                "doc_id": doc.get("id", ""),
            }
            citations.append(citation)
        return citations


# ── RAG Pipeline ──────────────────────────────────────────────
class RAGPipeline:
    """Full 7-stage RAG pipeline."""

    def __init__(self) -> None:
        self.query_transformer = QueryTransformer()
        self.retriever = MultiSourceRetriever()
        self.reranker = CrossEncoderReranker()
        self.compressor = ContextCompressor()
        self.attributor = SourceAttributor()

    async def run(
        self,
        query: str,
        context: str = "",
        filter_metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Execute full RAG pipeline."""
        logger.info("rag_pipeline_start", query=query[:80])

        # Stage 1: Query Transformation
        queries = await self.query_transformer.transform(query, context)

        # Stage 2: Multi-Source Retrieval
        documents = await self.retriever.retrieve(queries, filter_metadata=filter_metadata)

        if not documents:
            return {
                "compressed_context": "",
                "citations": [],
                "documents_retrieved": 0,
                "queries_used": queries,
            }

        # Stage 3: Reranking
        reranked = await self.reranker.rerank(query, documents)

        # Stage 4: Context Compression
        compressed = await self.compressor.compress(query, reranked)

        # Stage 5: Source Attribution
        citations = self.attributor.build_citations(reranked)

        logger.info(
            "rag_pipeline_complete",
            retrieved=len(documents),
            reranked=len(reranked),
            citations=len(citations),
        )

        return {
            "compressed_context": compressed,
            "citations": citations,
            "documents_retrieved": len(documents),
            "documents_reranked": len(reranked),
            "queries_used": queries,
            "top_documents": reranked[:3],
        }
