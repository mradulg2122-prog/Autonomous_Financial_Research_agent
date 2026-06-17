"""
ARA-1 News Intelligence Agent
Retrieves news and performs sentiment analysis.
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
async def run_news_intelligence_agent(state: ResearchState) -> dict[str, Any]:
    """News Intelligence Agent: collects news and performs sentiment analysis."""
    ticker = state.get("company_ticker", "")
    company_name = state.get("company_name", ticker)

    logger.info("news_intelligence_agent_start", ticker=ticker)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    tools_schema = registry.get_openai_schemas([
        "news_search", "web_search", "sentiment_analysis", "vector_db_store",
    ])

    messages = [
        {
            "role": "system",
            "content": (
                "You are a news intelligence analyst specializing in financial markets. "
                "Find recent news about the company, analyze sentiment, identify key themes, "
                "and flag any significant events that could impact the stock."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Collect and analyze news for {company_name} ({ticker}).\n"
                f"Find: recent earnings news, analyst upgrades/downgrades, and major events.\n"
                f"Analyze sentiment and identify investment-relevant signals.\n"
                f"Research context: {state['query']}"
            ),
        },
    ]

    news_findings: dict[str, Any] = {}
    tools_called: list[str] = []

    for _ in range(min(settings.max_tool_calls_per_agent, 6)):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("news_llm_error", error=str(exc))
            break

        msg = response.choices[0].message
        messages.append(safe_serialize_message(msg))

        if not msg.tool_calls:
            if msg.content:
                news_findings["intelligence_summary"] = msg.content
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

                if tool_name == "news_search":
                    existing = news_findings.get("articles", [])
                    news_findings["articles"] = existing + tool_result.get("articles", [])
                elif tool_name == "sentiment_analysis":
                    news_findings["sentiment"] = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str)[:3000],
                })
            except Exception as exc:
                logger.warning("news_tool_error", tool=tool_name, error=str(exc))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": str(exc)}),
                })

        if all_failed:
            break

    logger.info("news_intelligence_agent_complete", ticker=ticker, article_count=len(news_findings.get("articles", [])))

    return {
        "news_data": news_findings,
        "sentiment_data": news_findings.get("sentiment"),
        "agents_executed": ["news_intelligence_agent"],
        "tools_called": tools_called,
        "messages": [{
            "role": "news_intelligence_agent",
            "content": f"News analysis complete. Found {len(news_findings.get('articles', []))} articles.",
        }],
    }
