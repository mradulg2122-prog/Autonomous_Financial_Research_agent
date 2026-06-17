"""
ARA-1 Earnings Transcript Agent
Extracts management commentary and forward guidance from earnings calls.
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
async def run_earnings_transcript_agent(state: ResearchState) -> dict[str, Any]:
    """Earnings Transcript Agent: extracts management commentary and guidance."""
    ticker = state.get("company_ticker", "")
    company_name = state.get("company_name", ticker)

    logger.info("earnings_transcript_agent_start", ticker=ticker)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    tools_schema = registry.get_openai_schemas(["earnings_transcript", "web_search", "vector_db_store"])

    messages = [
        {
            "role": "system",
            "content": (
                "You are an earnings call analyst. Extract and interpret "
                "management commentary from earnings calls. Focus on: CEO/CFO commentary, "
                "forward guidance, revenue/margin outlook, and strategic initiatives."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analyze earnings call data for {company_name} ({ticker}).\n"
                f"Extract: management commentary on business performance, "
                f"forward guidance, and key strategic priorities.\n"
                f"Research context: {state['query']}"
            ),
        },
    ]

    earnings_findings: dict[str, Any] = {}
    tools_called: list[str] = []

    for _ in range(min(settings.max_tool_calls_per_agent, 5)):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("earnings_llm_error", error=str(exc))
            break

        msg = response.choices[0].message
        messages.append(safe_serialize_message(msg))

        if not msg.tool_calls:
            if msg.content:
                earnings_findings["analysis"] = msg.content
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

                if tool_name == "earnings_transcript":
                    earnings_findings["transcript_data"] = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str)[:3000],
                })
            except Exception as exc:
                logger.warning("earnings_tool_error", tool=tool_name, error=str(exc))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": str(exc)}),
                })

        if all_failed:
            break

    logger.info("earnings_transcript_agent_complete", ticker=ticker)

    return {
        "earnings_data": earnings_findings,
        "agents_executed": ["earnings_transcript_agent"],
        "tools_called": tools_called,
        "messages": [{
            "role": "earnings_transcript_agent",
            "content": f"Earnings transcript analysis complete for {ticker}.",
        }],
    }
