"""
ARA-1 LangGraph Workflow
Full compiled StateGraph with Plan-and-Execute architecture.
Agents run sequentially to respect Gemini free-tier rate limits (5 req/min).
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from langgraph.graph import StateGraph, END

from backend.agents.planner_agent import run_planner_agent
from backend.agents.sec_research_agent import run_sec_research_agent
from backend.agents.financial_data_agent import run_financial_data_agent
from backend.agents.news_intelligence_agent import run_news_intelligence_agent
from backend.agents.earnings_transcript_agent import run_earnings_transcript_agent
from backend.agents.fact_verification_agent import run_fact_verification_agent
from backend.agents.synthesis_agent import run_synthesis_agent
from backend.agents.report_writer_agent import run_report_writer_agent
from backend.agents.evaluation_agent import run_evaluation_agent
from backend.core.logging import get_logger
from backend.graph.state import ResearchState

logger = get_logger(__name__)

# Delay between agent calls to respect Gemini free-tier (5 req/min)
_INTER_AGENT_DELAY_SECONDS = 5


# ── Node Wrappers ─────────────────────────────────────────────

async def planner_node(state: ResearchState) -> dict[str, Any]:
    return await run_planner_agent(state)


async def sequential_research_node(state: ResearchState) -> dict[str, Any]:
    """
    Run SEC, Financial, News, and Earnings agents SEQUENTIALLY.
    This avoids hitting the Gemini free-tier rate limit (5 req/min).
    Each agent is run one after another with a small delay.
    """
    session_id = state.get("session_id", "")
    logger.info("sequential_research_start", session_id=session_id)

    merged: dict[str, Any] = {
        "agents_executed": [],
        "tools_called": [],
        "errors": [],
        "messages": [],
    }

    agents = [
        ("financial_data_agent", run_financial_data_agent),
        ("sec_research_agent",   run_sec_research_agent),
        ("news_intelligence_agent", run_news_intelligence_agent),
        ("earnings_transcript_agent", run_earnings_transcript_agent),
    ]

    for agent_name, agent_fn in agents:
        logger.info("running_agent", agent=agent_name, session_id=session_id)
        try:
            result = await agent_fn(state)
            # Merge results back into state (for next agent's reference)
            for key, val in result.items():
                if key in ("agents_executed", "tools_called", "errors", "messages"):
                    merged[key] = merged.get(key, []) + (val or [])
                elif val is not None:
                    merged[key] = val
                    # Also update state so next agent can reference it
                    state = {**state, key: val}  # type: ignore[assignment]
        except Exception as exc:
            logger.error("agent_error", agent=agent_name, error=str(exc))
            merged["errors"].append({"agent": agent_name, "error": str(exc)})

        # Polite delay between agents (avoid rate limit)
        await asyncio.sleep(_INTER_AGENT_DELAY_SECONDS)

    merged["status"] = "verifying"
    logger.info("sequential_research_complete", session_id=session_id)
    return merged


async def fact_verification_node(state: ResearchState) -> dict[str, Any]:
    return await run_fact_verification_agent(state)


async def synthesis_node(state: ResearchState) -> dict[str, Any]:
    return await run_synthesis_agent(state)


async def report_writer_node(state: ResearchState) -> dict[str, Any]:
    return await run_report_writer_agent(state)


async def evaluation_node(state: ResearchState) -> dict[str, Any]:
    return await run_evaluation_agent(state)


# ── Conditional Edges ─────────────────────────────────────────

def should_continue_after_plan(state: ResearchState) -> Literal["research", "error"]:
    """Always proceed — planner always produces a fallback plan."""
    if state.get("research_plan"):
        return "research"
    logger.warning("plan_missing", session_id=state.get("session_id"))
    return "error"


def should_continue_after_research(state: ResearchState) -> Literal["verify", "synthesize"]:
    """Always continue — even if data is partial, proceed to synthesis."""
    has_data = any([
        state.get("financial_data"),
        state.get("sec_data"),
        state.get("news_data"),
        state.get("earnings_data"),
    ])
    if not has_data:
        logger.warning("no_research_data", session_id=state.get("session_id"))
        # Still proceed — fact verification will handle empty state gracefully
    return "verify"


def should_continue_after_synthesis(state: ResearchState) -> Literal["report", "error"]:
    """Check if synthesis produced useful output."""
    if state.get("synthesis"):
        return "report"
    logger.warning("synthesis_empty", session_id=state.get("session_id"))
    return "error"


async def error_node(state: ResearchState) -> dict[str, Any]:
    """Handle terminal errors gracefully."""
    logger.error("workflow_error", session_id=state.get("session_id"), status=state.get("status"))
    return {
        "status": "failed",
        "messages": [{"role": "system", "content": "Research workflow encountered an unrecoverable error."}],
    }


# ── Build Graph ───────────────────────────────────────────────

def build_research_graph() -> StateGraph:
    """Build and return the compiled LangGraph research workflow."""
    graph = StateGraph(ResearchState)

    # Add all nodes
    graph.add_node("planner", planner_node)
    graph.add_node("sequential_research", sequential_research_node)
    graph.add_node("fact_verification", fact_verification_node)
    graph.add_node("synthesis_node", synthesis_node)
    graph.add_node("report_writer", report_writer_node)
    graph.add_node("evaluation_node", evaluation_node)
    graph.add_node("error_handler", error_node)

    # Entry point
    graph.set_entry_point("planner")

    # Conditional edge after planner
    graph.add_conditional_edges(
        "planner",
        should_continue_after_plan,
        {
            "research": "sequential_research",
            "error": "error_handler",
        },
    )

    # After research → fact verification (always)
    graph.add_conditional_edges(
        "sequential_research",
        should_continue_after_research,
        {
            "verify": "fact_verification",
            "synthesize": "synthesis_node",
        },
    )

    # Linear: fact verification → synthesis
    graph.add_edge("fact_verification", "synthesis_node")

    # Conditional: synthesis → report or error
    graph.add_conditional_edges(
        "synthesis_node",
        should_continue_after_synthesis,
        {
            "report": "report_writer",
            "error": "error_handler",
        },
    )

    graph.add_edge("report_writer", "evaluation_node")
    graph.add_edge("evaluation_node", END)
    graph.add_edge("error_handler", END)

    return graph


# Singleton compiled graph
_compiled_graph = None


def get_compiled_graph():
    """Get or create the compiled research graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_research_graph().compile()
    return _compiled_graph
