"""Initial ARA-1 database schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── research_sessions ──────────────────────────────────────
    op.create_table(
        'research_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('company_ticker', sa.String(20), nullable=True),
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('plan', JSONB, nullable=True),
        sa.Column('subtasks', JSONB, nullable=True),
        sa.Column('total_tool_calls', sa.Integer, nullable=True, server_default='0'),
        sa.Column('total_tokens_used', sa.BigInteger, nullable=True, server_default='0'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('duration_seconds', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_research_sessions_ticker', 'research_sessions', ['company_ticker'])
    op.create_index('ix_research_sessions_status', 'research_sessions', ['status'])
    op.create_index('ix_research_sessions_created', 'research_sessions', ['created_at'])

    # ── agent_traces ───────────────────────────────────────────
    op.create_table(
        'agent_traces',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('research_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('iteration', sa.Integer, nullable=False, server_default='0'),
        sa.Column('reasoning', sa.Text, nullable=True),
        sa.Column('errors', JSONB, nullable=True),
        sa.Column('input_data', JSONB, nullable=True),
        sa.Column('output_data', JSONB, nullable=True),
        sa.Column('tokens_used', sa.Integer, nullable=True),
        sa.Column('duration_ms', sa.Float, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_agent_traces_session', 'agent_traces', ['session_id'])
    op.create_index('ix_agent_traces_agent', 'agent_traces', ['agent_name'])

    # ── tool_calls ─────────────────────────────────────────────
    op.create_table(
        'tool_calls',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('research_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_trace_id', UUID(as_uuid=True), nullable=True),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('input_args', JSONB, nullable=True),
        sa.Column('output_data', JSONB, nullable=True),
        sa.Column('success', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('duration_ms', sa.Float, nullable=True),
        sa.Column('tokens_used', sa.Integer, nullable=True, server_default='0'),
        sa.Column('called_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_tool_calls_session', 'tool_calls', ['session_id'])
    op.create_index('ix_tool_calls_tool', 'tool_calls', ['tool_name'])

    # ── episodic_memories ──────────────────────────────────────
    op.create_table(
        'episodic_memories',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', UUID(as_uuid=True), nullable=True),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('company_ticker', sa.String(20), nullable=True),
        sa.Column('reasoning_path', JSONB, nullable=True),
        sa.Column('tools_used', JSONB, nullable=True),
        sa.Column('agents_executed', JSONB, nullable=True),
        sa.Column('errors_encountered', JSONB, nullable=True),
        sa.Column('conflicts_resolved', JSONB, nullable=True),
        sa.Column('final_report_id', UUID(as_uuid=True), nullable=True),
        sa.Column('evaluation_score', sa.Float, nullable=True),
        sa.Column('success', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('qdrant_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_episodic_memories_session', 'episodic_memories', ['session_id'])
    op.create_index('ix_episodic_memories_ticker', 'episodic_memories', ['company_ticker'])

    # ── reports ────────────────────────────────────────────────
    op.create_table(
        'reports',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('research_sessions.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('company_ticker', sa.String(20), nullable=True),
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('executive_summary', sa.Text, nullable=True),
        sa.Column('company_overview', sa.Text, nullable=True),
        sa.Column('financial_analysis', sa.Text, nullable=True),
        sa.Column('growth_analysis', sa.Text, nullable=True),
        sa.Column('profitability_analysis', sa.Text, nullable=True),
        sa.Column('competitive_position', sa.Text, nullable=True),
        sa.Column('risk_assessment', sa.Text, nullable=True),
        sa.Column('management_commentary', sa.Text, nullable=True),
        sa.Column('industry_outlook', sa.Text, nullable=True),
        sa.Column('valuation_metrics', sa.Text, nullable=True),
        sa.Column('investment_thesis', sa.Text, nullable=True),
        sa.Column('research_methodology', sa.Text, nullable=True),
        sa.Column('source_citations', JSONB, nullable=True),
        sa.Column('confidence_scores', JSONB, nullable=True),
        sa.Column('full_report_markdown', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_reports_session', 'reports', ['session_id'])
    op.create_index('ix_reports_ticker', 'reports', ['company_ticker'])

    # ── evaluation_results ─────────────────────────────────────
    op.create_table(
        'evaluation_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('research_sessions.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('overall_score', sa.Float, nullable=True),
        sa.Column('grade', sa.String(5), nullable=True),
        sa.Column('factual_accuracy', sa.Float, nullable=True),
        sa.Column('completeness', sa.Float, nullable=True),
        sa.Column('analytical_depth', sa.Float, nullable=True),
        sa.Column('reasoning_quality', sa.Float, nullable=True),
        sa.Column('tool_efficiency', sa.Float, nullable=True),
        sa.Column('memory_utilization', sa.Float, nullable=True),
        sa.Column('hallucination_rate', sa.Float, nullable=True),
        sa.Column('source_diversity', sa.Float, nullable=True),
        sa.Column('latency_score', sa.Float, nullable=True),
        sa.Column('error_recovery', sa.Float, nullable=True),
        sa.Column('report_quality', sa.Float, nullable=True),
        sa.Column('detailed_metrics', JSONB, nullable=True),
        sa.Column('benchmark_results', JSONB, nullable=True),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_evaluation_results_session', 'evaluation_results', ['session_id'])
    op.create_index('ix_evaluation_results_score', 'evaluation_results', ['overall_score'])


def downgrade() -> None:
    op.drop_table('evaluation_results')
    op.drop_table('reports')
    op.drop_table('episodic_memories')
    op.drop_table('tool_calls')
    op.drop_table('agent_traces')
    op.drop_table('research_sessions')
