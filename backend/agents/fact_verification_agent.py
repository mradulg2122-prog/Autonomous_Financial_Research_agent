"""
ARA-1 Fact Verification Agent
Verifies numerical claims and assigns confidence scores.
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


def _extract_all_claims(state: ResearchState) -> list[str]:
    """Extract verifiable claims from all collected research data."""
    claims = []
    fin = state.get("financial_data") or {}
    ratios = (fin.get("financials") or {}).get("key_ratios") or {}
    if ratios.get("revenue_ttm"):
        claims.append(f"Total revenue TTM: {ratios['revenue_ttm']}")
    if ratios.get("profit_margin"):
        claims.append(f"Net profit margin: {ratios['profit_margin']}")
    if ratios.get("pe_ratio"):
        claims.append(f"P/E ratio: {ratios['pe_ratio']}")
    if ratios.get("market_cap"):
        claims.append(f"Market cap: {ratios['market_cap']}")
    news = state.get("news_data") or {}
    for article in (news.get("articles") or [])[:3]:
        desc = article.get("description", "")
        if any(c in desc for c in ["$", "%", "billion", "million"]):
            claims.append(desc[:200])
    return claims[:15]


@with_retry(service="openai")
async def run_fact_verification_agent(state: ResearchState) -> dict[str, Any]:
    """Fact Verification Agent: verifies claims across all collected data."""
    ticker = state.get("company_ticker", "")
    logger.info("fact_verification_agent_start", ticker=ticker)

    claims = _extract_all_claims(state)

    # If no claims to verify, skip LLM call entirely
    if not claims:
        logger.info("fact_verification_skipped_no_claims", ticker=ticker)
        return {
            "fact_check_results": {"verified_claims": [], "summary": {"total": 0, "verified": 0}},
            "verified_claims": [],
            "agents_executed": ["fact_verification_agent"],
            "tools_called": [],
            "messages": [{"role": "fact_verification_agent", "content": "No claims to verify."}],
        }

    source_data: dict[str, Any] = {}
    if state.get("financial_data"):
        fin = state["financial_data"]
        source_data.update((fin.get("financials") or {}).get("key_ratios") or {})
        source_data.update(fin.get("calculated_ratios") or {})

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    tools_schema = registry.get_openai_schemas(["fact_checker", "financial_data_api"])

    messages = [
        {
            "role": "system",
            "content": (
                "You are a financial fact-checker. Verify numerical and factual claims. "
                "Cross-reference data from multiple sources and assign confidence scores."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Verify the following claims for {ticker}.\n\n"
                f"Claims:\n{json.dumps(claims, indent=2)}\n\n"
                f"Source data:\n{json.dumps(source_data, default=str)[:1500]}\n\n"
                "Use fact_checker to verify. Report confidence scores."
            ),
        },
    ]

    verification_results: dict[str, Any] = {}
    tools_called: list[str] = []

    for _ in range(min(settings.max_tool_calls_per_agent, 3)):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("fact_verification_llm_error", error=str(exc))
            break

        msg = response.choices[0].message
        messages.append(safe_serialize_message(msg))

        if not msg.tool_calls:
            if msg.content:
                verification_results["verification_summary"] = msg.content
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
                if tool_name == "fact_checker":
                    verification_results.update(tool_result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str)[:2000],
                })
            except Exception as exc:
                logger.warning("fact_tool_error", tool=tool_name, error=str(exc))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": str(exc)}),
                })

        if all_failed:
            break

    verified = verification_results.get("verified_claims", [])
    logger.info("fact_verification_agent_complete", ticker=ticker, verified=len(verified))

    return {
        "fact_check_results": verification_results,
        "verified_claims": verified,
        "agents_executed": ["fact_verification_agent"],
        "tools_called": tools_called,
        "messages": [{
            "role": "fact_verification_agent",
            "content": f"Fact verification complete. Verified {len(verified)} claims.",
        }],
    }
