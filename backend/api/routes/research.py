"""
ARA-1 Research API Routes
POST /research - Start a new research session
GET /research/{session_id} - Get session status and results
GET /research - List all sessions
WebSocket /ws/{session_id} - Real-time event stream
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.websocket import ws_manager
from backend.core.logging import get_logger
from backend.db.database import get_db_session, get_session
from backend.db.models import ResearchSession
from backend.graph.state import ResearchState
from backend.graph.workflow import get_compiled_graph
from backend.memory.short_term import ShortTermMemory
from backend.memory.episodic import EpisodicMemoryStore

logger = get_logger(__name__)

router = APIRouter(prefix="/research", tags=["research"])


# ── Request/Response Models ───────────────────────────────────

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=2000, description="Research query")
    company_ticker: Optional[str] = Field(None, max_length=10, description="Optional company ticker")
    company_name: Optional[str] = Field(None, max_length=255)


class ResearchResponse(BaseModel):
    session_id: str
    status: str
    message: str
    query: str
    created_at: str


class SessionStatusResponse(BaseModel):
    session_id: str
    query: str
    status: str
    company_ticker: Optional[str]
    company_name: Optional[str]
    agents_executed: Optional[list[str]]
    tools_used: Optional[list[str]]
    key_findings: Optional[list[str]]
    has_report: bool
    has_evaluation: bool
    created_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    error_message: Optional[str]


# ── Background Research Runner ────────────────────────────────

async def run_research_workflow(
    session_id: str,
    query: str,
    company_ticker: Optional[str],
    company_name: Optional[str],
) -> None:
    """Execute the full research workflow in the background."""
    from backend.db.models import ResearchSession, Report, EvaluationResult
    import sqlalchemy as sa

    start_time = datetime.utcnow()

    # Update session status to running
    async with get_db_session() as db:
        session_obj = await db.get(ResearchSession, uuid.UUID(session_id))
        if session_obj:
            session_obj.status = "planning"
            session_obj.started_at = start_time
            await db.flush()

    await ws_manager.broadcast_status(session_id, "planning", "Starting research planning...")

    # Build initial state
    initial_state: ResearchState = {
        "session_id": session_id,
        "query": query,
        "company_ticker": company_ticker,
        "company_name": company_name,
        "research_plan": None,
        "subtasks": [],
        "current_subtask_index": 0,
        "sec_data": None,
        "financial_data": None,
        "news_data": None,
        "earnings_data": None,
        "market_data": None,
        "company_profile_data": None,
        "peer_data": None,
        "risk_data": None,
        "sentiment_data": None,
        "vector_search_results": None,
        "fact_check_results": None,
        "verified_claims": [],
        "conflicts": [],
        "conflict_resolutions": [],
        "synthesis": None,
        "key_findings": [],
        "report": None,
        "report_sections": None,
        "evaluation": None,
        "iteration": 0,
        "agents_executed": [],
        "tools_called": [],
        "errors": [],
        "messages": [],
        "next_step": None,
        "status": "planning",
    }

    # Store initial state in short-term memory
    stm = ShortTermMemory(session_id)
    await stm.set("status", "planning")
    await stm.set("query", query)

    try:
        # Execute the graph
        graph = get_compiled_graph()
        final_state = await graph.ainvoke(initial_state)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Persist results to database
        async with get_db_session() as db:
            session_obj = await db.get(ResearchSession, uuid.UUID(session_id))
            if session_obj:
                session_obj.status = final_state.get("status", "complete")
                session_obj.completed_at = end_time
                session_obj.duration_seconds = duration
                session_obj.plan = final_state.get("research_plan")
                session_obj.subtasks = final_state.get("subtasks")
                session_obj.total_tool_calls = len(final_state.get("tools_called", []))
                session_obj.company_ticker = final_state.get("company_ticker") or company_ticker
                # Use resolved company_name from state; fall back to the original request name
                resolved_name = final_state.get("company_name")
                if not resolved_name or resolved_name == final_state.get("company_ticker"):
                    resolved_name = company_name or final_state.get("company_ticker")
                session_obj.company_name = resolved_name

                # Save report
                if final_state.get("report"):
                    report_data = final_state["report"]
                    from backend.db.models import Report as ReportModel
                    report = ReportModel(
                        session_id=uuid.UUID(session_id),
                        company_ticker=final_state.get("company_ticker"),
                        company_name=final_state.get("company_name"),
                        executive_summary=report_data.get("sections", {}).get("executive_summary"),
                        company_overview=report_data.get("sections", {}).get("company_overview"),
                        financial_analysis=report_data.get("sections", {}).get("financial_analysis"),
                        growth_analysis=report_data.get("sections", {}).get("growth_analysis"),
                        profitability_analysis=report_data.get("sections", {}).get("profitability_analysis"),
                        competitive_position=report_data.get("sections", {}).get("competitive_position"),
                        risk_assessment=report_data.get("sections", {}).get("risk_assessment"),
                        management_commentary=report_data.get("sections", {}).get("management_commentary"),
                        industry_outlook=report_data.get("sections", {}).get("industry_outlook"),
                        valuation_metrics=report_data.get("sections", {}).get("valuation_metrics"),
                        investment_thesis=report_data.get("sections", {}).get("investment_thesis"),
                        research_methodology=report_data.get("sections", {}).get("research_methodology"),
                        source_citations=report_data.get("source_citations"),
                        confidence_scores=report_data.get("confidence_scores"),
                        full_report_markdown=report_data.get("full_report_markdown"),
                    )
                    db.add(report)

                # Save evaluation
                if final_state.get("evaluation"):
                    eval_data = final_state["evaluation"]
                    from backend.db.models import EvaluationResult as EvalModel
                    category = eval_data.get("category_scores", {})
                    evaluation = EvalModel(
                        session_id=uuid.UUID(session_id),
                        overall_score=eval_data.get("overall_score"),
                        grade=eval_data.get("grade"),
                        factual_accuracy=category.get("factual_accuracy"),
                        completeness=category.get("completeness"),
                        analytical_depth=category.get("analytical_depth"),
                        reasoning_quality=category.get("reasoning_quality"),
                        tool_efficiency=category.get("tool_efficiency"),
                        memory_utilization=category.get("memory_utilization"),
                        hallucination_rate=category.get("hallucination_rate"),
                        source_diversity=category.get("source_diversity"),
                        latency_score=category.get("latency_score"),
                        error_recovery=category.get("error_recovery"),
                        report_quality=category.get("report_quality"),
                        detailed_metrics=eval_data.get("detailed_metrics"),
                    )
                    db.add(evaluation)

                await db.flush()

        # Store episodic memory
        episodic = EpisodicMemoryStore()
        await episodic.store_episode(
            session_id=session_id,
            query=query,
            company_ticker=final_state.get("company_ticker"),
            reasoning_path=[m for m in final_state.get("messages", [])],
            tools_used=list(set(final_state.get("tools_called", []))),
            agents_executed=list(set(final_state.get("agents_executed", []))),
            errors_encountered=final_state.get("errors", []),
            conflicts_resolved=final_state.get("conflict_resolutions", []),
            final_report_id=None,
            evaluation_score=(final_state.get("evaluation") or {}).get("overall_score"),
            success=final_state.get("status") == "complete",
        )

        await stm.set("status", "complete")
        await stm.set("agents_executed", list(set(final_state.get("agents_executed", []))))
        await stm.set("tools_used", list(set(final_state.get("tools_called", []))))
        await stm.set("key_findings", final_state.get("key_findings", []))
        await ws_manager.broadcast_status(session_id, "complete", "Research complete!")
        logger.info("research_workflow_complete", session_id=session_id, duration=duration)

    except Exception as exc:
        logger.error("research_workflow_error", session_id=session_id, error=str(exc))
        async with get_db_session() as db:
            session_obj = await db.get(ResearchSession, uuid.UUID(session_id))
            if session_obj:
                session_obj.status = "failed"
                session_obj.error_message = str(exc)
                session_obj.completed_at = datetime.utcnow()
                await db.flush()

        await stm.set("status", "failed")
        await ws_manager.broadcast_status(session_id, "failed", str(exc))


# ── API Endpoints ─────────────────────────────────────────────

@router.post("", response_model=ResearchResponse, status_code=202)
async def start_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> ResearchResponse:
    """Start a new autonomous research session."""
    session_id = str(uuid.uuid4())
    now = datetime.utcnow()

    session = ResearchSession(
        id=uuid.UUID(session_id),
        query=request.query,
        company_ticker=request.company_ticker,
        company_name=request.company_name,
        status="pending",
        created_at=now,
    )
    db.add(session)
    await db.flush()

    background_tasks.add_task(
        run_research_workflow,
        session_id=session_id,
        query=request.query,
        company_ticker=request.company_ticker,
        company_name=request.company_name,
    )

    logger.info("research_started", session_id=session_id, query=request.query[:100])

    return ResearchResponse(
        session_id=session_id,
        status="pending",
        message="Research session started. Connect to WebSocket for real-time updates.",
        query=request.query,
        created_at=now.isoformat(),
    )


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_research_status(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> SessionStatusResponse:
    """Get status and results of a research session."""
    try:
        stmt = (
            select(ResearchSession)
            .options(
                selectinload(ResearchSession.report),
                selectinload(ResearchSession.evaluation),
            )
            .where(ResearchSession.id == uuid.UUID(session_id))
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")

    # Also fetch from short-term memory for latest state
    stm = ShortTermMemory(session_id)
    agents = await stm.get("agents_executed") or []
    tools  = await stm.get("tools_used") or []
    findings = await stm.get("key_findings") or []

    return SessionStatusResponse(
        session_id=session_id,
        query=session.query,
        status=session.status,
        company_ticker=session.company_ticker,
        company_name=session.company_name,
        agents_executed=agents or None,
        tools_used=tools or None,
        key_findings=findings or None,
        has_report=bool(session.report),
        has_evaluation=bool(session.evaluation),
        created_at=session.created_at.isoformat(),
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        duration_seconds=session.duration_seconds,
        error_message=session.error_message,
    )


@router.get("")
async def list_research_sessions(
    limit: int = 20,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """List recent research sessions."""
    from sqlalchemy import select
    result = await db.execute(
        select(ResearchSession).order_by(ResearchSession.created_at.desc()).limit(limit)
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "session_id": str(s.id),
                "query": s.query[:100],
                "company_ticker": s.company_ticker,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "duration_seconds": s.duration_seconds,
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


# ── WebSocket Endpoint ────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time research event streaming."""
    await ws_manager.connect(websocket, session_id)
    try:
        # Send current state on connect
        stm = ShortTermMemory(session_id)
        status = await stm.get("status") or "unknown"
        await websocket.send_text(
            f'{{"type": "connected", "session_id": "{session_id}", "status": "{status}"}}'
        )

        while True:
            # Keep connection alive, handle ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, session_id)
