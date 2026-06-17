"""
ARA-1 Unit Tests — RAG Pipeline
Tests for query transformation, retrieval, reranking, and compression.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


@pytest.mark.asyncio
async def test_query_transformer_returns_alternatives():
    """QueryTransformer should return multiple query variants."""
    mock_result = {
        "alternatives": [
            "Apple Inc financial performance Q4",
            "AAPL revenue growth analysis",
            "Apple Inc earnings and margins",
        ],
        "hyde_excerpt": "Apple reported revenue of $394.3 billion with gross margin of 44.1%...",
    }
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_result)

    with patch("backend.rag.pipeline.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client

        from backend.rag.pipeline import QueryTransformer
        qt = QueryTransformer()
        queries = await qt.transform("Analyze Apple Inc financial performance")

    assert len(queries) >= 2
    assert "Analyze Apple Inc financial performance" in queries  # original always included


@pytest.mark.asyncio
async def test_multi_source_retriever_deduplicates():
    """MultiSourceRetriever should deduplicate results across query variants."""
    mock_doc_1 = {"id": "doc-001", "score": 0.92, "text": "Apple revenue $394B", "metadata": {}}
    mock_doc_2 = {"id": "doc-002", "score": 0.85, "text": "Apple margins 44%", "metadata": {}}

    with patch("backend.rag.pipeline.LongTermMemory") as mock_ltm_cls:
        mock_ltm = AsyncMock()
        # Same doc returned by both queries — should be deduplicated
        mock_ltm.search = AsyncMock(side_effect=[
            [mock_doc_1, mock_doc_2],
            [mock_doc_1],  # duplicate
        ])
        mock_ltm_cls.return_value = mock_ltm

        from backend.rag.pipeline import MultiSourceRetriever
        retriever = MultiSourceRetriever()
        results = await retriever.retrieve(
            queries=["AAPL financials", "Apple revenue"],
            top_k=10,
        )

    # Should have 2 unique docs (not 3)
    ids = [r["id"] for r in results]
    assert len(ids) == len(set(ids))
    assert "doc-001" in ids
    assert "doc-002" in ids


@pytest.mark.asyncio
async def test_rag_pipeline_returns_compressed_context():
    """Full RAG pipeline should return compressed context and citations."""
    mock_queries = ["AAPL", "Apple revenue", "Apple Inc financials"]
    mock_docs = [
        {"id": "d1", "score": 0.9, "text": "Apple revenue $394B in FY2024", "metadata": {"source": "SEC EDGAR"}},
        {"id": "d2", "score": 0.85, "text": "Apple gross margin 44.1%", "metadata": {"source": "Yahoo Finance"}},
    ]
    compressed = "Apple FY2024: Revenue $394B, Gross Margin 44.1%"

    with patch("backend.rag.pipeline.QueryTransformer") as mock_qt_cls, \
         patch("backend.rag.pipeline.MultiSourceRetriever") as mock_ret_cls, \
         patch("backend.rag.pipeline.CrossEncoderReranker") as mock_rr_cls, \
         patch("backend.rag.pipeline.ContextCompressor") as mock_comp_cls:

        mock_qt = AsyncMock()
        mock_qt.transform = AsyncMock(return_value=mock_queries)
        mock_qt_cls.return_value = mock_qt

        mock_ret = AsyncMock()
        mock_ret.retrieve = AsyncMock(return_value=mock_docs)
        mock_ret_cls.return_value = mock_ret

        mock_rr = AsyncMock()
        mock_rr.rerank = AsyncMock(return_value=mock_docs)
        mock_rr_cls.return_value = mock_rr

        mock_comp = AsyncMock()
        mock_comp.compress = AsyncMock(return_value=compressed)
        mock_comp_cls.return_value = mock_comp

        from backend.rag.pipeline import RAGPipeline
        pipeline = RAGPipeline()
        result = await pipeline.run("Apple financial performance 2024")

    assert result["compressed_context"] == compressed
    assert result["documents_retrieved"] == 2
    assert len(result["citations"]) == 2


@pytest.mark.asyncio
async def test_rag_pipeline_empty_results():
    """RAG pipeline should handle zero retrieval results gracefully."""
    with patch("backend.rag.pipeline.QueryTransformer") as mock_qt_cls, \
         patch("backend.rag.pipeline.MultiSourceRetriever") as mock_ret_cls:

        mock_qt = AsyncMock()
        mock_qt.transform = AsyncMock(return_value=["query"])
        mock_qt_cls.return_value = mock_qt

        mock_ret = AsyncMock()
        mock_ret.retrieve = AsyncMock(return_value=[])
        mock_ret_cls.return_value = mock_ret

        from backend.rag.pipeline import RAGPipeline
        pipeline = RAGPipeline()
        result = await pipeline.run("Unknown company XYZ")

    assert result["compressed_context"] == ""
    assert result["documents_retrieved"] == 0
    assert result["citations"] == []
