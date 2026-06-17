"""
ARA-1 Unit Tests — Agents
Tests that verify agent logic without calling real LLMs.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


def _make_state(overrides=None):
    """Build a minimal ResearchState for testing."""
    base = {
        "session_id": "test-session-001",
        "query": "Analyze Apple Inc. financials",
        "company_ticker": "AAPL",
        "company_name": "Apple Inc.",
        "research_plan": None,
        "subtasks": [],
        "current_subtask_index": 0,
        "sec_data": None,
        "financial_data": None,
        "news_data": None,
        "earnings_data": None,
        "market_data": None,
        "company_profile_data": None,
        "peer_data": None,
        "risk_data": None,
        "sentiment_data": None,
        "vector_search_results": None,
        "fact_check_results": None,
        "verified_claims": [],
        "conflicts": [],
        "conflict_resolutions": [],
        "synthesis": None,
        "key_findings": [],
        "report": None,
        "report_sections": None,
        "evaluation": None,
        "iteration": 0,
        "agents_executed": [],
        "tools_called": [],
        "errors": [],
        "messages": [],
        "next_step": None,
        "status": "planning",
    }
    if overrides:
        base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_planner_agent_returns_plan():
    """Planner agent should return a research_plan and subtasks."""
    mock_plan = {
        "objective": "Analyze AAPL financials",
        "company_ticker": "AAPL",
        "company_name": "Apple Inc.",
        "research_type": "financial_summary",
        "priority_sources": ["financial_data", "sec_filing"],
        "subtasks": [
            {"id": 1, "name": "SEC Filing", "agent": "sec_research_agent", "tools": ["sec_filing_search"], "priority": "high"},
            {"id": 2, "name": "Financial Data", "agent": "financial_data_agent", "tools": ["financial_data_api"], "priority": "high"},
        ],
        "estimated_duration_minutes": 5,
        "special_focus_areas": [],
    }

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_plan)

    with patch("backend.agents.planner_agent.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client

        from backend.agents.planner_agent import run_planner_agent
        result = await run_planner_agent(_make_state())

    assert result["research_plan"] is not None
    assert result["company_ticker"] == "AAPL"
    assert result["company_name"] == "Apple Inc."
    assert len(result["subtasks"]) == 2
    assert result["status"] == "researching"
    assert "planner_agent" in result["agents_executed"]


@pytest.mark.asyncio
async def test_planner_agent_no_ticker():
    """Planner agent should extract ticker from query if not provided."""
    mock_plan = {
        "objective": "Research Microsoft",
        "company_ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "research_type": "full_report",
        "subtasks": [],
        "estimated_duration_minutes": 10,
    }

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_plan)

    with patch("backend.agents.planner_agent.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client

        from backend.agents.planner_agent import run_planner_agent
        state = _make_state({"company_ticker": None, "query": "Research Microsoft Corporation MSFT"})
        result = await run_planner_agent(state)

    assert result["company_ticker"] == "MSFT"


@pytest.mark.asyncio
async def test_evaluation_agent_computes_grade():
    """Evaluation agent should produce a grade and overall score."""
    state = _make_state({
        "financial_data": {"financials": {"key_ratios": {"revenue_ttm": 400e9}}, "summary": "Strong revenue"},
        "sec_data": {"filings": [{"type": "10-K"}], "analysis": "Solid filing"},
        "news_data": {"articles": [{"title": "AAPL up", "description": "Apple stock rises"}]},
        "earnings_data": {"analysis": "Strong earnings"},
        "report_sections": {
            "executive_summary": "A" * 200,
            "financial_analysis": "B" * 200,
            "risk_assessment": "C" * 200,
            "competitive_position": "D" * 200,
            "investment_thesis": "E" * 200,
        },
        "verified_claims": [{"claim": "Revenue $400B", "verified": True}],
        "tools_called": ["financial_data_api", "sec_filing_search", "news_search", "market_data_tool"],
        "agents_executed": ["planner_agent", "sec_research_agent", "financial_data_agent"],
        "errors": [],
    })

    mock_scores = {
        "factual_accuracy": 0.85,
        "analytical_depth": 0.80,
        "reasoning_quality": 0.82,
        "report_quality": 0.88,
        "investment_thesis_clarity": 0.79,
        "risk_coverage": 0.76,
        "valuation_rigor": 0.72,
        "commentary_insight": 0.70,
    }
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_scores)

    with patch("backend.agents.evaluation_agent.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client

        from backend.agents.evaluation_agent import run_evaluation_agent
        result = await run_evaluation_agent(state)

    assert "evaluation" in result
    eval_data = result["evaluation"]
    assert "overall_score" in eval_data
    assert "grade" in eval_data
    assert eval_data["grade"] in ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]
    assert 0.0 <= eval_data["overall_score"] <= 1.0
    assert result["status"] == "complete"
    assert len(eval_data["detailed_metrics"]) >= 25


def test_evaluation_metrics_module():
    """Metrics module should define 25+ metrics across 11 categories."""
    from backend.evaluation.metrics import METRICS, MetricCategory, get_metric_names

    names = get_metric_names()
    assert len(names) >= 25, f"Expected 25+ metrics, got {len(names)}"

    categories = {m.category for m in METRICS}
    assert len(categories) == len(list(MetricCategory))


def test_compute_category_averages():
    """compute_category_averages should handle partial data."""
    from backend.evaluation.metrics import compute_category_averages, compute_overall_score, score_to_grade

    metrics = {
        "factual_accuracy_score": 0.9,
        "fact_verification_rate": 0.8,
        "report_completeness": 0.85,
        "tool_efficiency_score": 0.75,
        "hallucination_risk_score": 0.95,
    }
    cats = compute_category_averages(metrics)
    assert "factual_accuracy" in cats
    assert cats["factual_accuracy"] > 0

    overall = compute_overall_score(cats)
    assert 0.0 <= overall <= 1.0

    grade = score_to_grade(0.92)
    assert grade == "A"
    assert score_to_grade(0.94) == "A+"
    assert score_to_grade(0.50) == "F"
