"""
ARA-1 Financial Data Agent
Retrieves and analyzes revenue, profitability, ratios, and cash flow.
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
async def run_financial_data_agent(state: ResearchState) -> dict[str, Any]:
    """
    Financial Data Agent: comprehensive financial data collection and analysis.
    """
    ticker = state.get("company_ticker", "")
    if not ticker:
        return {"financial_data": {"error": "No ticker"}, "agents_executed": ["financial_data_agent"]}

    logger.info("financial_data_agent_start", ticker=ticker)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    tools_schema = registry.get_openai_schemas([
        "financial_data_api", "calculation_engine", "market_data_tool",
        "company_profile", "vector_db_store",
    ])

    messages = [
        {
            "role": "system",
            "content": (
                "You are a financial data analyst. Collect comprehensive financial data for the company: "
                "income statement, balance sheet, cash flow, key ratios, and market data. "
                "Then run calculations to derive additional metrics."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Collect and analyze financial data for {ticker} ({state.get('company_name', '')}).\n"
                f"Required: income statement trends, profitability metrics, cash flow analysis, "
                f"key valuation ratios, and market performance.\n"
                f"Research context: {state['query']}"
            ),
        },
    ]

    financial_findings: dict[str, Any] = {}
    tools_called: list[str] = []

    for _ in range(min(settings.max_tool_calls_per_agent, 8)):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("financial_llm_error", error=str(exc))
            break

        msg = response.choices[0].message
        messages.append(safe_serialize_message(msg))

        if not msg.tool_calls:
            if msg.content:
                financial_findings["summary"] = msg.content
            break

        all_failed = True
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            tools_called.append(tool_name)
            try:
                args = json.loads(tc.function.arguments)
                result = await registry.execute(tool_name, args, session_id=state["session_id"])
                tool_result = result.get("result", {})
                all_failed = False

                if tool_name == "financial_data_api":
                    financial_findings["financials"] = tool_result
                elif tool_name == "calculation_engine":
                    financial_findings["calculated_ratios"] = tool_result.get("calculations", {})
                elif tool_name == "market_data_tool":
                    financial_findings["market_data"] = tool_result
                elif tool_name == "company_profile":
                    financial_findings["profile"] = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str)[:3000],
                })
            except Exception as exc:
                logger.warning("financial_tool_error", tool=tool_name, error=str(exc))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": str(exc)}),
                })

        if all_failed:
            break

    logger.info("financial_data_agent_complete", ticker=ticker)

    return {
        "financial_data": financial_findings,
        "market_data": financial_findings.get("market_data"),
        "company_profile_data": financial_findings.get("profile"),
        "agents_executed": ["financial_data_agent"],
        "tools_called": tools_called,
        "messages": [{
            "role": "financial_data_agent",
            "content": f"Financial data collection complete for {ticker}.",
        }],
    }
