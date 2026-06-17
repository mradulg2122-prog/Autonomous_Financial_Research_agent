"""
ARA-1 SEC Research Agent
Retrieves SEC filings, extracts risk factors and MD&A insights.
"""
from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.core.utils import safe_serialize_message
from backend.graph.state import ResearchState
from backend.tools.registry import registry

logger = get_logger(__name__)


@with_retry(service="openai")
async def run_sec_research_agent(state: ResearchState) -> dict[str, Any]:
    """
    SEC Research Agent: fetches SEC filings and extracts key insights.
    Uses ReAct loop (Reason → Act → Observe) with OpenAI tool calling.
    """
    ticker = state.get("company_ticker", "")
    if not ticker:
        return {
            "sec_data": {"error": "No ticker available"},
            "agents_executed": ["sec_research_agent"],
        }

    logger.info("sec_research_agent_start", ticker=ticker)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    tools_schema = registry.get_openai_schemas(["sec_filing_search", "vector_db_store", "vector_db_search"])

    messages = [
        {
            "role": "system",
            "content": (
                "You are an SEC filing analyst. Retrieve and analyze SEC filings for the given company. "
                "Focus on: risk factors, MD&A insights, and business description. "
                "Use sec_filing_search to retrieve filings."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Research SEC filings for {ticker} ({state.get('company_name', '')}). "
                f"Retrieve the most recent 10-K or 10-Q. "
                f"Extract risk factors and MD&A highlights."
            ),
        },
    ]

    sec_findings: dict[str, Any] = {}
    max_iterations = min(settings.max_tool_calls_per_agent, 5)
    tools_called: list[str] = []

    for _ in range(max_iterations):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("sec_llm_error", error=str(exc))
            break

        msg = response.choices[0].message
        messages.append(safe_serialize_message(msg))

        if not msg.tool_calls:
            if msg.content:
                sec_findings["analysis"] = msg.content
            break

        # Execute tool calls
        all_failed = True
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            tools_called.append(tool_name)
            try:
                args = json.loads(tc.function.arguments)
                result = await registry.execute(tool_name, args, session_id=state["session_id"])
                tool_result = result.get("result", {})
                all_failed = False

                if tool_name == "sec_filing_search":
                    sec_findings["filings"] = tool_result.get("filings", [])
                    sec_findings["cik"] = tool_result.get("cik")
                    sec_findings["ticker"] = tool_result.get("ticker")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str)[:3000],
                })
            except Exception as exc:
                logger.warning("sec_tool_error", tool=tool_name, error=str(exc))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": str(exc)}),
                })

        if all_failed:
            break

    logger.info("sec_research_agent_complete", ticker=ticker, findings_keys=list(sec_findings.keys()))

    return {
        "sec_data": sec_findings,
        "agents_executed": ["sec_research_agent"],
        "tools_called": tools_called,
        "messages": [{
            "role": "sec_research_agent",
            "content": f"SEC research complete for {ticker}. Retrieved {len(sec_findings.get('filings', []))} filings.",
        }],
    }
