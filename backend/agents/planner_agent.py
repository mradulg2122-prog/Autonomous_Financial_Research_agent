"""
ARA-1 Planner Agent
Generates a structured research plan and decomposes the query into subtasks.
"""
from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.errors import PlannerError
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.core.utils import parse_json_robustly
from backend.graph.state import ResearchState

logger = get_logger(__name__)

PLANNER_SYSTEM = """You are a senior equity research planner at a top investment bank.
Create precise, actionable research plans for financial analysis.
ALWAYS respond with valid JSON only. No markdown, no explanation, just JSON."""


def _build_fallback_plan(ticker: str, query: str) -> dict:
    """Generate a minimal fallback plan if the LLM fails to return valid JSON."""
    return {
        "objective": f"Comprehensive investment research for {ticker}",
        "company_ticker": ticker,
        "company_name": ticker,
        "research_type": "full_report",
        "priority_sources": ["financial_data", "news", "sec_filing"],
        "subtasks": [
            {
                "id": 1,
                "name": "Collect Financial Data",
                "description": f"Retrieve financial metrics and ratios for {ticker}",
                "agent": "financial_data_agent",
                "tools": ["financial_data_api", "market_data_tool"],
                "expected_output": "Financial statements and key ratios",
                "priority": "high",
            },
            {
                "id": 2,
                "name": "News & Sentiment Analysis",
                "description": f"Collect recent news and analyze sentiment for {ticker}",
                "agent": "news_intelligence_agent",
                "tools": ["news_search", "sentiment_analysis"],
                "expected_output": "News articles and sentiment scores",
                "priority": "high",
            },
            {
                "id": 3,
                "name": "SEC Filing Research",
                "description": f"Retrieve SEC filings for {ticker}",
                "agent": "sec_research_agent",
                "tools": ["sec_filing_search"],
                "expected_output": "Risk factors and MD&A insights",
                "priority": "medium",
            },
        ],
        "estimated_duration_minutes": 5,
        "special_focus_areas": [],
    }


@with_retry(service="openai")
async def run_planner_agent(state: ResearchState) -> dict[str, Any]:
    """
    Planner Agent: analyzes the query and generates a structured research plan.
    Returns updated state dict.
    """
    logger.info("planner_agent_start", session_id=state["session_id"], query=state["query"][:100])

    ticker = state.get("company_ticker", "UNKNOWN")
    company_name = state.get("company_name", ticker)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Simplified prompt that Gemini handles reliably
    prompt = f"""Create a financial research plan for this query: {state["query"]}

Company: {company_name} (Ticker: {ticker})

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "objective": "what we are researching",
  "company_ticker": "{ticker}",
  "company_name": "{company_name}",
  "research_type": "full_report",
  "priority_sources": ["financial_data", "news", "sec_filing"],
  "subtasks": [
    {{
      "id": 1,
      "name": "Collect Financial Data",
      "description": "Retrieve financial metrics for {ticker}",
      "agent": "financial_data_agent",
      "tools": ["financial_data_api", "market_data_tool"],
      "expected_output": "Financial statements and key ratios",
      "priority": "high"
    }},
    {{
      "id": 2,
      "name": "News and Sentiment",
      "description": "Collect news and sentiment for {ticker}",
      "agent": "news_intelligence_agent",
      "tools": ["news_search", "sentiment_analysis"],
      "expected_output": "News and sentiment scores",
      "priority": "high"
    }},
    {{
      "id": 3,
      "name": "SEC Filing Research",
      "description": "Retrieve SEC filings for {ticker}",
      "agent": "sec_research_agent",
      "tools": ["sec_filing_search"],
      "expected_output": "Risk factors and MD&A",
      "priority": "medium"
    }}
  ],
  "estimated_duration_minutes": 5,
  "special_focus_areas": []
}}"""

    plan: dict = {}

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
        )

        content = (response.choices[0].message.content or "").strip()

        if not content:
            logger.warning("planner_empty_response", ticker=ticker, using_fallback=True)
            plan = _build_fallback_plan(ticker, state["query"])
        else:
            try:
                plan = parse_json_robustly(content)
            except (ValueError, json.JSONDecodeError) as exc:
                logger.warning("planner_parse_error", error=str(exc), using_fallback=True)
                plan = _build_fallback_plan(ticker, state["query"])

    except Exception as exc:
        logger.error("planner_llm_error", error=str(exc), using_fallback=True)
        plan = _build_fallback_plan(ticker, state["query"])

    # Ensure required fields exist
    resolved_ticker = plan.get("company_ticker") or ticker
    resolved_name = plan.get("company_name") or company_name
    subtasks = plan.get("subtasks") or []

    if not subtasks:
        plan = _build_fallback_plan(resolved_ticker, state["query"])
        subtasks = plan.get("subtasks", [])

    logger.info(
        "planner_agent_complete",
        ticker=resolved_ticker,
        subtask_count=len(subtasks),
        research_type=plan.get("research_type"),
    )

    return {
        "research_plan": plan,
        "subtasks": subtasks,
        "company_ticker": resolved_ticker,
        "company_name": resolved_name,
        "current_subtask_index": 0,
        "status": "researching",
        "agents_executed": ["planner_agent"],
        "messages": [{
            "role": "planner",
            "content": f"Research plan created with {len(subtasks)} subtasks for {resolved_name} ({resolved_ticker})",
        }],
    }
