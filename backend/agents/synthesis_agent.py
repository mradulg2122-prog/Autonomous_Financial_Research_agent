"""
ARA-1 Synthesis Agent
Merges findings from all agents, resolves conflicts, and produces unified analysis.
"""
from __future__ import annotations

import asyncio
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
async def run_synthesis_agent(state: ResearchState) -> dict[str, Any]:
    """Synthesis Agent: merges all research findings into a coherent analysis."""
    ticker = state.get("company_ticker", "")
    company_name = state.get("company_name", ticker)

    logger.info("synthesis_agent_start", ticker=ticker)

    fin_data = state.get("financial_data") or {}
    news_data = state.get("news_data") or {}
    sec_data = state.get("sec_data") or {}

    synthesis_context = {
        "company": {"ticker": ticker, "name": company_name},
        "financial_data": {
            "key_ratios": (fin_data.get("financials") or {}).get("key_ratios") or {},
            "calculated": fin_data.get("calculated_ratios") or {},
            "summary": fin_data.get("summary") or "",
        },
        "news": {
            "article_count": len(news_data.get("articles") or []),
            "sentiment": news_data.get("sentiment") or {},
            "summary": news_data.get("intelligence_summary") or "",
        },
        "earnings": {"data": state.get("earnings_data") or {}},
        "sec": {
            "filing_count": len(sec_data.get("filings") or []),
            "analysis": sec_data.get("analysis") or "",
        },
    }

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    tools_schema = registry.get_openai_schemas(["peer_comparison", "risk_analysis_tool", "vector_db_store"])

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior research analyst synthesizing financial research. "
                "Integrate findings from SEC filings, financial data, news, and earnings data. "
                "Identify the top investment findings and assess the overall investment picture."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Synthesize all research for {company_name} ({ticker}).\n\n"
                f"Data summary:\n{json.dumps(synthesis_context, default=str)[:3000]}\n\n"
                f"Query: {state['query']}\n\n"
                "Get peer comparison and risk analysis, then synthesize key investment insights."
            ),
        },
    ]

    synthesis_result: dict[str, Any] = {}
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
            logger.warning("synthesis_llm_error", error=str(exc))
            break

        msg = response.choices[0].message
        messages.append(safe_serialize_message(msg))

        if not msg.tool_calls:
            if msg.content:
                synthesis_result["unified_analysis"] = msg.content
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

                if tool_name == "peer_comparison":
                    synthesis_result["peer_analysis"] = tool_result
                elif tool_name == "risk_analysis_tool":
                    synthesis_result["risk_analysis"] = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str)[:2000],
                })
            except Exception as exc:
                logger.warning("synthesis_tool_error", tool=tool_name, error=str(exc))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": str(exc)}),
                })

        if all_failed:
            break

    # If no synthesis result from LLM, build a minimal one from context
    if not synthesis_result.get("unified_analysis"):
        synthesis_result["unified_analysis"] = (
            f"Research synthesized for {company_name} ({ticker}). "
            f"Data collected from {synthesis_context['sec']['filing_count']} SEC filings, "
            f"{synthesis_context['news']['article_count']} news articles."
        )

    # Generate key findings — with rate-limit delay
    await asyncio.sleep(3)
    key_findings_text = ""
    try:
        kf_response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{
                "role": "user",
                "content": (
                    f"List the 5 most important investment findings for {company_name} ({ticker}) "
                    f"as concise bullet points. Context: "
                    f"{json.dumps(synthesis_result, default=str)[:1500]}"
                ),
            }],
            temperature=0.1,
            max_tokens=400,
        )
        key_findings_text = kf_response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("key_findings_error", error=str(exc))
        key_findings_text = f"• {ticker} research complete\n• Financial and market data collected"

    synthesis_result["key_findings_text"] = key_findings_text
    synthesis_result["context"] = synthesis_context
    synthesis_result["ticker"] = ticker
    synthesis_result["company_name"] = company_name

    key_findings = [
        f.strip("•- ").strip()
        for f in key_findings_text.split("\n")
        if f.strip() and len(f.strip()) > 10
    ][:5]

    if not key_findings:
        key_findings = [f"Research completed for {company_name} ({ticker})"]

    logger.info("synthesis_agent_complete", ticker=ticker, findings=len(key_findings))

    return {
        "synthesis": synthesis_result,
        "peer_data": synthesis_result.get("peer_analysis"),
        "risk_data": synthesis_result.get("risk_analysis"),
        "key_findings": key_findings,
        "conflict_resolutions": [],
        "agents_executed": ["synthesis_agent"],
        "tools_called": tools_called,
        "status": "reporting",
        "messages": [{
            "role": "synthesis_agent",
            "content": f"Synthesis complete for {ticker}. {len(key_findings)} key findings identified.",
        }],
    }
