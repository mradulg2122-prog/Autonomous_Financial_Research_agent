"""
ARA-1 Agents API Routes
GET /agents/registry - List all available agents
GET /agents/traces/{session_id} - Get agent trace for a session
GET /agents/tools - List all registered tools with schemas
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.database import get_session
from backend.db.models import AgentTrace, ToolCall
from backend.tools.registry import registry

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/registry")
async def list_agents() -> dict:
    """List all available research agents."""
    return {
        "agents": [
            {
                "name": "planner_agent",
                "description": "Generates research plan and decomposes query into subtasks",
                "role": "Planning",
            },
            {
                "name": "sec_research_agent",
                "description": "Retrieves SEC filings, extracts risks and MD&A insights",
                "role": "SEC Research",
            },
            {
                "name": "financial_data_agent",
                "description": "Collects revenue, profitability, ratios, and cash flow data",
                "role": "Financial Data",
            },
            {
                "name": "news_intelligence_agent",
                "description": "Retrieves news and performs sentiment analysis",
                "role": "News Intelligence",
            },
            {
                "name": "earnings_transcript_agent",
                "description": "Extracts management commentary and forward guidance",
                "role": "Earnings Analysis",
            },
            {
                "name": "fact_verification_agent",
                "description": "Verifies numerical claims and assigns confidence scores",
                "role": "Verification",
            },
            {
                "name": "synthesis_agent",
                "description": "Merges findings and resolves conflicts",
                "role": "Synthesis",
            },
            {
                "name": "report_writer_agent",
                "description": "Generates institutional-quality investment research report",
                "role": "Report Writing",
            },
            {
                "name": "evaluation_agent",
                "description": "Scores research quality on 25+ metrics",
                "role": "Evaluation",
            },
        ],
        "total": 9,
    }


@router.get("/tools")
async def list_tools(include_schema: bool = False) -> dict:
    """List all registered tools."""
    tool_names = registry.list_tools()
    tools = []
    for name in tool_names:
        tool = registry.get(name)
        entry: dict = {
            "name": tool.name,
            "description": tool.description,
            "timeout_seconds": tool.timeout,
        }
        if include_schema:
            entry["schema"] = tool.to_openai_schema()
        tools.append(entry)
    return {"tools": tools, "total": len(tools)}


@router.get("/traces/{session_id}")
async def get_agent_traces(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Get all agent trace records for a session."""
    result = await db.execute(
        select(AgentTrace)
        .where(AgentTrace.session_id == uuid.UUID(session_id))
        .order_by(AgentTrace.started_at)
    )
    traces = result.scalars().all()

    tool_result = await db.execute(
        select(ToolCall)
        .where(ToolCall.session_id == uuid.UUID(session_id))
        .order_by(ToolCall.called_at)
    )
    tool_calls = tool_result.scalars().all()

    return {
        "session_id": session_id,
        "agent_traces": [
            {
                "id": str(t.id),
                "agent_name": t.agent_name,
                "status": t.status,
                "iteration": t.iteration,
                "reasoning": t.reasoning,
                "tokens_used": t.tokens_used,
                "started_at": t.started_at.isoformat(),
                "duration_ms": t.duration_ms,
            }
            for t in traces
        ],
        "tool_calls": [
            {
                "id": str(tc.id),
                "tool_name": tc.tool_name,
                "success": tc.success,
                "duration_ms": tc.duration_ms,
                "called_at": tc.called_at.isoformat(),
                "error_message": tc.error_message,
            }
            for tc in tool_calls
        ],
        "total_agents": len(traces),
        "total_tool_calls": len(tool_calls),
    }
