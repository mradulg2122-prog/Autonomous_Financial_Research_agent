"""
ARA-1 Report Writer Agent
Generates the institutional-quality 14-section investment research report.
"""
from __future__ import annotations

import json
from typing import Any

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.graph.state import ResearchState
from backend.tools.registry import registry

logger = get_logger(__name__)


@with_retry(service="openai")
async def run_report_writer_agent(state: ResearchState) -> dict[str, Any]:
    """Report Writer Agent: generates the full investment research report."""
    ticker = state.get("company_ticker", "")
    company_name = state.get("company_name", ticker)

    logger.info("report_writer_agent_start", ticker=ticker)

    # Compile all research data for the report
    research_data: dict[str, Any] = {
        "company": {"ticker": ticker, "name": company_name},
        "query": state["query"],
        "key_findings": state.get("key_findings", []),
        "financial_data": state.get("financial_data") or {},
        "sec_data": state.get("sec_data") or {},
        "news_data": {
            "sentiment": state.get("sentiment_data") or {},
            "article_count": len((state.get("news_data") or {}).get("articles") or []),
            "summary": (state.get("news_data") or {}).get("intelligence_summary", ""),
        },
        "earnings_data": state.get("earnings_data") or {},
        "peer_data": state.get("peer_data") or {},
        "risk_data": state.get("risk_data") or {},
        "synthesis": state.get("synthesis") or {},
        "verified_claims": state.get("verified_claims") or [],
        "conflict_resolutions": state.get("conflict_resolutions") or [],
        "market_data": state.get("market_data") or {},
    }

    # Generate full report using the report_generator tool
    result = await registry.execute(
        "report_generator",
        {
            "ticker": ticker,
            "company_name": company_name,
            "research_data": research_data,
            "section": "full_report",
        },
        session_id=state["session_id"],
    )

    report_data = result.get("result", {})

    # Build confidence scores for each section
    confidence_scores = _compute_confidence_scores(state)

    # Build source citations
    citations = _build_citations(state)

    # Add confidence and citations to report
    report_data["confidence_scores"] = confidence_scores
    report_data["source_citations"] = citations

    logger.info("report_writer_agent_complete", ticker=ticker, sections=len(report_data.get("sections", {})))

    return {
        "report": report_data,
        "report_sections": report_data.get("sections", {}),
        "agents_executed": ["report_writer_agent"],
        "tools_called": ["report_generator"],
        "status": "evaluating",
        "messages": [{
            "role": "report_writer_agent",
            "content": f"Full research report generated for {company_name} ({ticker}).",
        }],
    }


def _compute_confidence_scores(state: ResearchState) -> dict[str, float]:
    """Calculate per-section confidence scores based on data availability."""
    scores: dict[str, float] = {}

    has_financials = bool(state.get("financial_data"))
    has_sec = bool((state.get("sec_data") or {}).get("filings"))
    has_news = bool((state.get("news_data") or {}).get("articles"))
    has_earnings = bool(state.get("earnings_data"))
    has_peers = bool(state.get("peer_data"))
    verified_count = len(state.get("verified_claims") or [])

    scores["executive_summary"] = min(0.95, 0.5 + (0.1 * sum([has_financials, has_sec, has_news, has_earnings])))
    scores["financial_analysis"] = 0.95 if has_financials else 0.4
    scores["risk_assessment"] = 0.90 if has_sec else 0.6
    scores["competitive_position"] = 0.85 if has_peers else 0.5
    scores["management_commentary"] = 0.80 if has_earnings else 0.4
    scores["news_sentiment"] = 0.90 if has_news else 0.3
    scores["overall"] = round(sum(scores.values()) / len(scores), 3)
    scores["fact_verification_rate"] = min(1.0, verified_count / max(1, 10))

    return scores


def _build_citations(state: ResearchState) -> list[dict[str, str]]:
    """Build source citation list from all data sources used."""
    citations: list[dict[str, str]] = []

    if state.get("financial_data"):
        citations.append({
            "source": "Yahoo Finance",
            "tier": "Tier 2",
            "data_type": "Financial metrics, market data",
            "url": f"https://finance.yahoo.com/quote/{state.get('company_ticker', '')}",
        })

    if (state.get("sec_data") or {}).get("filings"):
        ticker = state.get("company_ticker", "")
        cik = (state.get("sec_data") or {}).get("cik", "")
        citations.append({
            "source": "SEC EDGAR",
            "tier": "Tier 1",
            "data_type": "10-K, 10-Q SEC filings",
            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
        })

    if (state.get("news_data") or {}).get("articles"):
        citations.append({
            "source": "NewsAPI / DuckDuckGo News",
            "tier": "Tier 4",
            "data_type": "News articles and press releases",
            "url": "https://newsapi.org",
        })

    if state.get("earnings_data"):
        citations.append({
            "source": "Yahoo Finance Earnings",
            "tier": "Tier 3",
            "data_type": "Earnings history and estimates",
            "url": f"https://finance.yahoo.com/quote/{state.get('company_ticker', '')}/financials",
        })

    return citations
