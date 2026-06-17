"""
ARA-1 SQLAlchemy ORM Models
Tables: ResearchSession, AgentTrace, ToolCall, EpisodicMemory, Report, EvaluationResult
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base


def now_utc() -> datetime:
    return datetime.utcnow()


class ResearchSession(Base):
    """Represents a single research request lifecycle."""
    __tablename__ = "research_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    company_ticker: Mapped[Optional[str]] = mapped_column(String(20))
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # Values: pending | planning | researching | synthesizing | reporting | complete | failed

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)

    # Metadata
    plan: Mapped[Optional[dict]] = mapped_column(JSON)
    subtasks: Mapped[Optional[list]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    total_tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)

    # Relationships
    agent_traces: Mapped[list[AgentTrace]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    report: Mapped[Optional[Report]] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    evaluation: Mapped[Optional[EvaluationResult]] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    episodic_memories: Mapped[list[EpisodicMemory]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AgentTrace(Base):
    """Records one agent's execution within a session."""
    __tablename__ = "agent_traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_sessions.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="running")
    # Values: running | complete | failed | skipped

    input_data: Mapped[Optional[dict]] = mapped_column(JSON)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    errors: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)

    session: Mapped[ResearchSession] = relationship(back_populates="agent_traces")


class ToolCall(Base):
    """Records a single tool invocation."""
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_sessions.id"), nullable=False
    )
    agent_trace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_traces.id")
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_args: Mapped[Optional[dict]] = mapped_column(JSON)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    called_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    session: Mapped[ResearchSession] = relationship(back_populates="tool_calls")


class EpisodicMemory(Base):
    """Long-term episodic memory record — one per research session."""
    __tablename__ = "episodic_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_sessions.id"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    company_ticker: Mapped[Optional[str]] = mapped_column(String(20))

    # Research trajectory
    reasoning_path: Mapped[Optional[list]] = mapped_column(JSON)
    tools_used: Mapped[Optional[list]] = mapped_column(JSON)
    agents_executed: Mapped[Optional[list]] = mapped_column(JSON)
    errors_encountered: Mapped[Optional[list]] = mapped_column(JSON)
    conflicts_resolved: Mapped[Optional[list]] = mapped_column(JSON)

    # Outcome
    final_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    evaluation_score: Mapped[Optional[float]] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    qdrant_id: Mapped[Optional[str]] = mapped_column(String(100))  # Vector DB ref

    session: Mapped[ResearchSession] = relationship(back_populates="episodic_memories")


class Report(Base):
    """Generated investment research report."""
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_sessions.id"), nullable=False, unique=True
    )
    company_ticker: Mapped[Optional[str]] = mapped_column(String(20))
    company_name: Mapped[Optional[str]] = mapped_column(String(255))

    # Sections
    executive_summary: Mapped[Optional[str]] = mapped_column(Text)
    company_overview: Mapped[Optional[str]] = mapped_column(Text)
    financial_analysis: Mapped[Optional[str]] = mapped_column(Text)
    growth_analysis: Mapped[Optional[str]] = mapped_column(Text)
    profitability_analysis: Mapped[Optional[str]] = mapped_column(Text)
    competitive_position: Mapped[Optional[str]] = mapped_column(Text)
    risk_assessment: Mapped[Optional[str]] = mapped_column(Text)
    management_commentary: Mapped[Optional[str]] = mapped_column(Text)
    industry_outlook: Mapped[Optional[str]] = mapped_column(Text)
    valuation_metrics: Mapped[Optional[str]] = mapped_column(Text)
    investment_thesis: Mapped[Optional[str]] = mapped_column(Text)
    research_methodology: Mapped[Optional[str]] = mapped_column(Text)
    source_citations: Mapped[Optional[list]] = mapped_column(JSON)
    confidence_scores: Mapped[Optional[dict]] = mapped_column(JSON)

    # Full markdown
    full_report_markdown: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    session: Mapped[ResearchSession] = relationship(back_populates="report")


class EvaluationResult(Base):
    """Evaluation scores for a completed research session."""
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_sessions.id"), nullable=False, unique=True
    )

    # Aggregate
    overall_score: Mapped[Optional[float]] = mapped_column(Float)
    grade: Mapped[Optional[str]] = mapped_column(String(5))

    # Category Scores (0.0 – 1.0)
    factual_accuracy: Mapped[Optional[float]] = mapped_column(Float)
    completeness: Mapped[Optional[float]] = mapped_column(Float)
    analytical_depth: Mapped[Optional[float]] = mapped_column(Float)
    reasoning_quality: Mapped[Optional[float]] = mapped_column(Float)
    tool_efficiency: Mapped[Optional[float]] = mapped_column(Float)
    memory_utilization: Mapped[Optional[float]] = mapped_column(Float)
    hallucination_rate: Mapped[Optional[float]] = mapped_column(Float)
    source_diversity: Mapped[Optional[float]] = mapped_column(Float)
    latency_score: Mapped[Optional[float]] = mapped_column(Float)
    error_recovery: Mapped[Optional[float]] = mapped_column(Float)
    report_quality: Mapped[Optional[float]] = mapped_column(Float)

    # Detailed metrics dict (all 25+ metrics)
    detailed_metrics: Mapped[Optional[dict]] = mapped_column(JSON)
    benchmark_results: Mapped[Optional[dict]] = mapped_column(JSON)

    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    session: Mapped[ResearchSession] = relationship(back_populates="evaluation")
