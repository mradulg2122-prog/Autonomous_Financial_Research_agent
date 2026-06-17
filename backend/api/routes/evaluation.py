"""
ARA-1 Evaluation API Routes
GET /evaluation/{session_id} - Get evaluation for a session
GET /evaluation/benchmarks/run - Run benchmark suite
GET /evaluation/leaderboard - Rank all sessions by score
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.database import get_session
from backend.db.models import EvaluationResult, ResearchSession
from backend.evaluation.benchmarks import run_all_benchmarks
from backend.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/{session_id}")
async def get_evaluation(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Get evaluation results for a session."""
    result = await db.execute(
        select(EvaluationResult).where(
            EvaluationResult.session_id == uuid.UUID(session_id)
        )
    )
    eval_result = result.scalar_one_or_none()
    if not eval_result:
        raise HTTPException(status_code=404, detail="Evaluation not found for this session")

    return {
        "session_id": session_id,
        "overall_score": eval_result.overall_score,
        "grade": eval_result.grade,
        "category_scores": {
            "factual_accuracy": eval_result.factual_accuracy,
            "completeness": eval_result.completeness,
            "analytical_depth": eval_result.analytical_depth,
            "reasoning_quality": eval_result.reasoning_quality,
            "tool_efficiency": eval_result.tool_efficiency,
            "memory_utilization": eval_result.memory_utilization,
            "hallucination_rate": eval_result.hallucination_rate,
            "source_diversity": eval_result.source_diversity,
            "latency_score": eval_result.latency_score,
            "error_recovery": eval_result.error_recovery,
            "report_quality": eval_result.report_quality,
        },
        "detailed_metrics": eval_result.detailed_metrics,
        "benchmark_results": eval_result.benchmark_results,
        "evaluated_at": eval_result.evaluated_at.isoformat(),
    }


@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Get top-scoring research sessions."""
    result = await db.execute(
        select(EvaluationResult, ResearchSession)
        .join(ResearchSession, EvaluationResult.session_id == ResearchSession.id)
        .order_by(EvaluationResult.overall_score.desc())
        .limit(limit)
    )
    rows = result.all()
    return {
        "leaderboard": [
            {
                "rank": i + 1,
                "session_id": str(ev.session_id),
                "query": sess.query[:80],
                "company_ticker": sess.company_ticker,
                "overall_score": ev.overall_score,
                "grade": ev.grade,
                "evaluated_at": ev.evaluated_at.isoformat(),
            }
            for i, (ev, sess) in enumerate(rows)
        ],
        "total": len(rows),
    }


@router.post("/benchmarks/run")
async def run_benchmarks(
    background_tasks: BackgroundTasks,
) -> dict:
    """Trigger the automated benchmark suite in the background."""
    background_tasks.add_task(run_all_benchmarks)
    return {
        "message": "Benchmark suite started in background",
        "benchmarks": [
            "Company Profile",
            "Financial Summary",
            "Risk Assessment",
            "Peer Comparison",
            "Earnings Analysis",
            "Industry Research",
            "Investment Thesis",
            "Full Institutional Report",
        ],
    }
