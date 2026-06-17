"""
ARA-1 Unit Tests — Tools
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_calculation_engine_profitability():
    """Test calculation engine computes profitability metrics."""
    from backend.tools.calculation_engine import calculation_engine

    data = {
        "totalRevenue": 100_000_000,
        "grossProfit": 60_000_000,
        "ebit": 30_000_000,
        "netIncome": 20_000_000,
        "ebitda": 35_000_000,
        "returnOnEquity": 0.25,
        "returnOnAssets": 0.15,
    }

    result = await calculation_engine(financial_data=data, calculations=["profitability"])
    assert "calculations" in result
    prof = result["calculations"].get("profitability", {})
    assert prof.get("gross_margin") == pytest.approx(0.6, rel=0.01)
    assert prof.get("roe") == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_calculation_engine_leverage():
    """Test leverage ratios."""
    from backend.tools.calculation_engine import calculation_engine

    data = {
        "debtToEquity": 1.5,
        "totalDebt": 50_000_000,
        "totalAssets": 100_000_000,
    }

    result = await calculation_engine(financial_data=data, calculations=["leverage"])
    assert "calculations" in result
    lev = result["calculations"].get("leverage", {})
    assert lev.get("debt_to_equity") == pytest.approx(1.5)
    assert lev.get("debt_to_assets") == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_fact_checker_empty_claims():
    """Test fact checker handles empty input gracefully."""
    from backend.tools.fact_checker import fact_checker

    with patch("backend.tools.fact_checker.AsyncOpenAI"):
        result = await fact_checker(claims=[], source_data={})
        assert result["verified"] == [] or "verified_claims" in result or result.get("summary", {}).get("total") == 0


def test_conflict_resolver_tier_priority():
    """Test conflict resolver prefers lower tier source."""
    from backend.conflict.resolver import ConflictResolver

    resolver = ConflictResolver()
    resolution = resolver.resolve(
        field="revenue",
        value_a="$100B",
        source_a="SEC EDGAR",
        value_b="$95B",
        source_b="DuckDuckGo",
    )
    assert resolution["chosen_value"] == "$100B"
    assert resolution["chosen_tier"] == 1


def test_conflict_resolver_same_tier_confidence():
    """Test same-tier conflict resolved by confidence."""
    from backend.conflict.resolver import ConflictResolver

    resolver = ConflictResolver()
    resolution = resolver.resolve(
        field="eps",
        value_a="$4.50",
        source_a="Yahoo Finance",
        value_b="$4.20",
        source_b="Alpha Vantage",
        confidence_a=0.9,
        confidence_b=0.7,
    )
    assert resolution["chosen_value"] == "$4.50"


def test_settings_config():
    """Test settings load correctly with defaults."""
    from backend.core.config import settings
    assert settings.app_name == "ARA-1"
    assert settings.openai_model == "gpt-4o"
    assert settings.qdrant_vector_size == 3072


def test_tool_registry():
    """Test tool registry has all 15 required tools."""
    import backend.tools  # Triggers registration
    from backend.tools.registry import registry

    required_tools = [
        "sec_filing_search", "financial_data_api", "earnings_transcript",
        "web_search", "news_search", "sentiment_analysis", "peer_comparison",
        "vector_db_search", "vector_db_store", "fact_checker", "report_generator",
        "calculation_engine", "company_profile", "market_data_tool", "risk_analysis_tool",
    ]

    registered = registry.list_tools()
    for tool in required_tools:
        assert tool in registered, f"Tool '{tool}' not registered"


def test_openai_schemas_valid():
    """Test all tools produce valid OpenAI function-calling schemas."""
    import backend.tools  # noqa
    from backend.tools.registry import registry

    schemas = registry.get_openai_schemas()
    for schema in schemas:
        assert schema["type"] == "function"
        func = schema["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
