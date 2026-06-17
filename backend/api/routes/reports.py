"""
ARA-1 Reports API Routes
GET /reports/{session_id} - Get full report
GET /reports/{session_id}/markdown - Get raw markdown
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.database import get_session
from backend.db.models import Report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{session_id}")
async def get_report(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Get the full research report for a session."""
    result = await db.execute(
        select(Report).where(Report.session_id == uuid.UUID(session_id))
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "session_id": session_id,
        "company_ticker": report.company_ticker,
        "company_name": report.company_name,
        "sections": {
            "executive_summary": report.executive_summary,
            "company_overview": report.company_overview,
            "financial_analysis": report.financial_analysis,
            "growth_analysis": report.growth_analysis,
            "profitability_analysis": report.profitability_analysis,
            "competitive_position": report.competitive_position,
            "risk_assessment": report.risk_assessment,
            "management_commentary": report.management_commentary,
            "industry_outlook": report.industry_outlook,
            "valuation_metrics": report.valuation_metrics,
            "investment_thesis": report.investment_thesis,
            "research_methodology": report.research_methodology,
        },
        "source_citations": report.source_citations,
        "confidence_scores": report.confidence_scores,
        "created_at": report.created_at.isoformat(),
    }


@router.get("/{session_id}/markdown", response_class=PlainTextResponse)
async def get_report_markdown(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> str:
    """Get the full report as raw Markdown."""
    result = await db.execute(
        select(Report).where(Report.session_id == uuid.UUID(session_id))
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report.full_report_markdown or "# Report\n\nNo content available."


@router.get("")
async def list_reports(
    limit: int = 20,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """List all generated reports."""
    result = await db.execute(
        select(Report).order_by(Report.created_at.desc()).limit(limit)
    )
    reports = result.scalars().all()
    return {
        "reports": [
            {
                "report_id": str(r.id),
                "session_id": str(r.session_id),
                "company_ticker": r.company_ticker,
                "company_name": r.company_name,
                "created_at": r.created_at.isoformat(),
            }
            for r in reports
        ],
        "total": len(reports),
    }
