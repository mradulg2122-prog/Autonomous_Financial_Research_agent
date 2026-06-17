"""
ARA-1 End-to-End Test — Full Research Workflow
Runs a complete research session against mocked external services.
"""
import pytest
import asyncio
import uuid
import json
from unittest.mock import AsyncMock, patch, MagicMock


def _make_openai_response(content: str, tool_calls=None):
    """Build a mock OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.model_dump = MagicMock(return_value={"role": "assistant", "content": content})

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_research_workflow_aapl():
    """
    E2E: Full research workflow for AAPL with all external calls mocked.
    Verifies: planner → parallel research → verification → synthesis → report → evaluation.
    """
    session_id = str(uuid.uuid4())

    # ── Mock Plans ────────────────────────────────────────────
    plan_json = json.dumps({
        "objective": "Comprehensive AAPL analysis",
        "company_ticker": "AAPL",
        "company_name": "Apple Inc.",
        "research_type": "full_report",
        "priority_sources": ["sec_filing", "financial_data"],
        "subtasks": [
            {"id": 1, "name": "SEC", "agent": "sec_research_agent", "tools": ["sec_filing_search"], "priority": "high"},
            {"id": 2, "name": "Financial", "agent": "financial_data_agent", "tools": ["financial_data_api"], "priority": "high"},
        ],
        "estimated_duration_minutes": 5,
        "special_focus_areas": [],
    })

    quality_json = json.dumps({
        "factual_accuracy": 0.88,
        "analytical_depth": 0.85,
        "reasoning_quality": 0.87,
        "report_quality": 0.90,
        "investment_thesis_clarity": 0.83,
        "risk_coverage": 0.82,
        "valuation_rigor": 0.79,
        "commentary_insight": 0.78,
    })

    mock_report_sections = {
        "executive_summary": "Apple Inc. (AAPL) is a leading consumer technology company. " * 20,
        "company_overview": "Apple designs, manufactures, and markets smartphones. " * 20,
        "financial_analysis": "Revenue grew 6% YoY to $394.3B. Gross margin 44.1%. " * 15,
        "growth_analysis": "iPhone drives 52% of revenue. Services segment growing 16% YoY. " * 15,
        "profitability_analysis": "Net income $97B. FCF generation $99.6B. " * 15,
        "competitive_position": "Apple leads premium smartphone market with 18% global share. " * 15,
        "risk_assessment": "Key risks: China concentration, regulatory, FX headwinds. " * 15,
        "management_commentary": "CEO Tim Cook highlighted India expansion and AI integration. " * 15,
        "industry_outlook": "Smartphone market growing 3% CAGR. AI integration a key theme. " * 15,
        "valuation_metrics": "P/E 28x vs sector 22x. PEG 2.1. DCF fair value $195-215. " * 15,
        "investment_thesis": "Bull: AI supercycle. Base: Steady growth. Bear: China risk. " * 15,
        "research_methodology": "Data sourced from SEC EDGAR, Yahoo Finance, and news APIs. " * 10,
    }

    report_full_md = "# Apple Inc. (AAPL) — Investment Research Report\n\n" + \
                     "\n".join(f"## {k}\n{v}" for k, v in mock_report_sections.items())

    call_count = {"n": 0}

    def make_response(content="", **kw):
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1:
            return _make_openai_response(plan_json)  # planner
        elif n <= 5:
            return _make_openai_response("Analysis complete.")  # research agents
        elif n == 6:
            return _make_openai_response(json.dumps({"verified_claims": [{"claim": "Revenue $394B", "verified": True, "confidence": 0.95}], "summary": {"total": 1, "verified": 1, "disputed": 0}}))
        elif n == 7:
            return _make_openai_response("Synthesis complete with 5 key findings.")
        elif n == 8:
            return _make_openai_response("Key findings identified.")
        elif n <= 20:
            # report sections
            section_keys = list(mock_report_sections.keys())
            idx = (n - 9) % len(section_keys)
            return _make_openai_response(list(mock_report_sections.values())[idx])
        elif n == 21:
            return _make_openai_response(quality_json)  # evaluation quality
        return _make_openai_response("OK")

    mock_financial_data = {
        "ticker": "AAPL",
        "key_ratios": {
            "market_cap": 3_000_000_000_000,
            "revenue_ttm": 394_300_000_000,
            "pe_ratio": 28.5,
            "profit_margin": 0.247,
            "gross_margin": 0.441,
            "debt_to_equity": 1.87,
        },
        "source": "Yahoo Finance",
    }

    mock_sec_data = {
        "ticker": "AAPL",
        "cik": "0000320193",
        "filings": [
            {"type": "10-K", "date": "2024-11-01", "url": "https://sec.gov/..."},
        ],
        "source": "SEC EDGAR",
    }

    mock_news = {
        "query": "Apple",
        "articles": [
            {"title": "Apple reports record services revenue", "description": "Services hit $24B in Q4.", "source": "Reuters"},
            {"title": "Apple Vision Pro sales disappoint", "description": "Mixed reality headset sales below expectations.", "source": "Bloomberg"},
        ],
    }

    mock_sentiment = {
        "overall_sentiment": "slightly_positive",
        "sentiment_score": 0.62,
        "bull_signals": ["Services growth", "India expansion"],
        "bear_signals": ["Vision Pro sales", "China headwinds"],
    }

    mock_peer_data = {
        "ticker": "AAPL",
        "peers": [
            {"ticker": "MSFT", "market_cap": 3_200_000_000_000, "pe_ratio": 34.2},
            {"ticker": "GOOGL", "market_cap": 2_100_000_000_000, "pe_ratio": 24.1},
        ],
    }

    mock_risk_data = {
        "ticker": "AAPL",
        "overall_risk_rating": "Medium",
        "overall_risk_score": 0.38,
        "top_risks": ["China revenue concentration", "Regulatory antitrust pressure", "FX headwinds"],
        "risk_matrix": [],
    }

    async def mock_tool_execute(tool_name, args, session_id=None):
        results = {
            "financial_data_api": mock_financial_data,
            "market_data_tool": {"ticker": "AAPL", "current_price": 211.45, "period_return_pct": 18.3},
            "company_profile": {"ticker": "AAPL", "longName": "Apple Inc.", "sector": "Technology"},
            "calculation_engine": {"calculations": {"profitability": {"gross_margin": 0.441}}},
            "sec_filing_search": mock_sec_data,
            "news_search": mock_news,
            "web_search": {"results": [], "query": args.get("query", "")},
            "sentiment_analysis": mock_sentiment,
            "earnings_transcript": {"ticker": "AAPL", "quarters": []},
            "peer_comparison": mock_peer_data,
            "fact_checker": {"verified_claims": [{"claim": "Revenue $394B", "verified": True, "confidence": 0.95}], "summary": {"total": 1, "verified": 1, "disputed": 0}},
            "risk_analysis_tool": mock_risk_data,
            "vector_db_store": {"id": str(uuid.uuid4()), "success": True},
            "vector_db_search": {"results": [], "query": ""},
            "report_generator": {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "sections": mock_report_sections,
                "full_report_markdown": report_full_md,
                "confidence_scores": {"overall": 0.87},
                "source_citations": [{"source": "SEC EDGAR", "tier": "Tier 1"}],
            },
        }
        return {"success": True, "result": results.get(tool_name, {}), "tool": tool_name, "duration_ms": 100}

    with patch("backend.agents.planner_agent.AsyncOpenAI") as mock_openai_cls, \
         patch("backend.agents.sec_research_agent.AsyncOpenAI") as mock_sec_openai, \
         patch("backend.agents.financial_data_agent.AsyncOpenAI") as mock_fin_openai, \
         patch("backend.agents.news_intelligence_agent.AsyncOpenAI") as mock_news_openai, \
         patch("backend.agents.earnings_transcript_agent.AsyncOpenAI") as mock_earn_openai, \
         patch("backend.agents.fact_verification_agent.AsyncOpenAI") as mock_fact_openai, \
         patch("backend.agents.synthesis_agent.AsyncOpenAI") as mock_synth_openai, \
         patch("backend.agents.report_writer_agent.registry") as mock_reg_rw, \
         patch("backend.agents.synthesis_agent.registry") as mock_reg_synth, \
         patch("backend.agents.evaluation_agent.AsyncOpenAI") as mock_eval_openai:

        for openai_mock in [mock_openai_cls, mock_sec_openai, mock_fin_openai, mock_news_openai,
                            mock_earn_openai, mock_fact_openai, mock_synth_openai, mock_eval_openai]:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=make_response)
            openai_mock.return_value = mock_client

        mock_reg_rw.execute = AsyncMock(side_effect=mock_tool_execute)
        mock_reg_synth.execute = AsyncMock(side_effect=mock_tool_execute)
        mock_reg_synth.get_openai_schemas = MagicMock(return_value=[])

        with patch("backend.agents.sec_research_agent.registry") as mock_reg_sec, \
             patch("backend.agents.financial_data_agent.registry") as mock_reg_fin, \
             patch("backend.agents.news_intelligence_agent.registry") as mock_reg_news, \
             patch("backend.agents.earnings_transcript_agent.registry") as mock_reg_earn, \
             patch("backend.agents.fact_verification_agent.registry") as mock_reg_fact:

            for reg_mock in [mock_reg_sec, mock_reg_fin, mock_reg_news, mock_reg_earn, mock_reg_fact]:
                reg_mock.execute = AsyncMock(side_effect=mock_tool_execute)
                reg_mock.get_openai_schemas = MagicMock(return_value=[])

            from backend.graph.state import ResearchState
            from backend.graph.workflow import build_research_graph

            initial_state: ResearchState = {
                "session_id": session_id,
                "query": "Generate a comprehensive investment research report for Apple Inc. (AAPL)",
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

            graph = build_research_graph().compile()
            final_state = await graph.ainvoke(initial_state)

    # ── Assertions ────────────────────────────────────────────
    assert final_state["company_ticker"] == "AAPL"
    assert final_state["research_plan"] is not None
    assert final_state["status"] in ("complete", "evaluating", "reporting")
    assert "planner_agent" in final_state.get("agents_executed", [])

    # Report should have been generated
    report = final_state.get("report")
    assert report is not None
    sections = final_state.get("report_sections") or report.get("sections", {})
    assert len(sections) >= 5

    # Evaluation
    evaluation = final_state.get("evaluation")
    assert evaluation is not None
    assert "overall_score" in evaluation
    assert "grade" in evaluation
    assert 0.0 <= evaluation["overall_score"] <= 1.0

    # Messages were accumulated
    assert len(final_state.get("messages", [])) >= 3
