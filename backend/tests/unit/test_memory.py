"""
ARA-1 Unit Tests — Memory System
Tests for Redis short-term, Qdrant long-term, and PostgreSQL episodic memory.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


@pytest.mark.asyncio
async def test_short_term_memory_set_get():
    """ShortTermMemory set/get should round-trip JSON values."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=json.dumps({"value": 42}))

    with patch("backend.memory.short_term.get_redis", return_value=mock_redis):
        from backend.memory.short_term import ShortTermMemory
        stm = ShortTermMemory("test-session-001")
        await stm.set("test_field", {"value": 42})
        result = await stm.get("test_field")

    assert result == {"value": 42}


@pytest.mark.asyncio
async def test_short_term_memory_returns_none_on_miss():
    """ShortTermMemory get should return None on cache miss."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("backend.memory.short_term.get_redis", return_value=mock_redis):
        from backend.memory.short_term import ShortTermMemory
        stm = ShortTermMemory("test-session-002")
        result = await stm.get("nonexistent_key")

    assert result is None


@pytest.mark.asyncio
async def test_short_term_memory_append_list():
    """ShortTermMemory list operations should work correctly."""
    mock_redis = AsyncMock()
    mock_redis.rpush = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.lrange = AsyncMock(return_value=[
        json.dumps({"tool": "sec_filing_search", "output": {"filings": []}}),
    ])

    with patch("backend.memory.short_term.get_redis", return_value=mock_redis):
        from backend.memory.short_term import ShortTermMemory
        stm = ShortTermMemory("test-session-003")
        await stm.store_tool_output("sec_filing_search", {"filings": []})
        outputs = await stm.get_tool_outputs()

    assert len(outputs) == 1
    assert outputs[0]["tool"] == "sec_filing_search"


@pytest.mark.asyncio
async def test_long_term_memory_store():
    """LongTermMemory store should embed and upsert to Qdrant."""
    mock_vector = [0.1] * 3072

    with patch("backend.memory.long_term.embed_text", return_value=mock_vector), \
         patch("backend.memory.long_term.get_qdrant") as mock_get_qdrant:

        mock_client = AsyncMock()
        mock_client.upsert = AsyncMock(return_value=MagicMock())
        mock_get_qdrant.return_value = mock_client

        from backend.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        doc_id = await ltm.store(
            text="Apple revenue grew 5% YoY",
            metadata={"type": "financial_fact", "ticker": "AAPL"},
        )

    assert doc_id is not None
    assert isinstance(doc_id, str)
    mock_client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_long_term_memory_search():
    """LongTermMemory search should return ranked documents."""
    mock_vector = [0.1] * 3072
    mock_result = MagicMock()
    mock_result.id = "doc-001"
    mock_result.score = 0.92
    mock_result.payload = {
        "text": "Apple revenue $400B",
        "type": "financial_fact",
        "ticker": "AAPL",
    }

    with patch("backend.memory.long_term.embed_text", return_value=mock_vector), \
         patch("backend.memory.long_term.get_qdrant") as mock_get_qdrant:

        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=[mock_result])
        mock_get_qdrant.return_value = mock_client

        from backend.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        results = await ltm.search("Apple revenue", top_k=5)

    assert len(results) == 1
    assert results[0]["score"] == pytest.approx(0.92)
    assert results[0]["text"] == "Apple revenue $400B"
    assert results[0]["metadata"]["ticker"] == "AAPL"


def test_conflict_resolver_batch():
    """ConflictResolver batch resolution should handle multiple conflicts."""
    from backend.conflict.resolver import ConflictResolver

    resolver = ConflictResolver()
    conflicts = [
        {
            "field": "revenue",
            "value_a": "$394B", "source_a": "SEC EDGAR",
            "value_b": "$389B", "source_b": "web_search",
        },
        {
            "field": "eps",
            "value_a": "$6.11", "source_a": "Yahoo Finance",
            "value_b": "$5.89", "source_b": "DuckDuckGo",
            "confidence_a": 0.9, "confidence_b": 0.5,
        },
    ]
    resolutions = resolver.resolve_batch(conflicts)
    assert len(resolutions) == 2
    assert resolutions[0]["chosen_value"] == "$394B"   # SEC wins over web
    assert resolutions[1]["chosen_value"] == "$6.11"   # Yahoo confidence wins

    log = resolver.get_audit_log()
    assert "revenue" in log
    assert "eps" in log
