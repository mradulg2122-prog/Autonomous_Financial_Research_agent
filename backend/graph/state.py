"""
ARA-1 LangGraph State Definition
TypedDict state schema for the full research workflow graph.
"""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict, Annotated
import operator


class ResearchState(TypedDict):
    """Full state passed through the LangGraph research workflow."""

    # ── Identity ──────────────────────────────────────────────
    session_id: str
    query: str
    company_ticker: Optional[str]
    company_name: Optional[str]

    # ── Plan ──────────────────────────────────────────────────
    research_plan: Optional[dict[str, Any]]
    subtasks: Annotated[list[dict], operator.add]
    current_subtask_index: int

    # ── Research Data ─────────────────────────────────────────
    sec_data: Optional[dict[str, Any]]
    financial_data: Optional[dict[str, Any]]
    news_data: Optional[dict[str, Any]]
    earnings_data: Optional[dict[str, Any]]
    market_data: Optional[dict[str, Any]]
    company_profile_data: Optional[dict[str, Any]]
    peer_data: Optional[dict[str, Any]]
    risk_data: Optional[dict[str, Any]]
    sentiment_data: Optional[dict[str, Any]]
    vector_search_results: Optional[list[dict]]

    # ── Verification ──────────────────────────────────────────
    fact_check_results: Optional[dict[str, Any]]
    verified_claims: Annotated[list[dict], operator.add]
    conflicts: Annotated[list[dict], operator.add]
    conflict_resolutions: Annotated[list[dict], operator.add]

    # ── Synthesis ─────────────────────────────────────────────
    synthesis: Optional[dict[str, Any]]
    key_findings: Annotated[list[str], operator.add]

    # ── Report ────────────────────────────────────────────────
    report: Optional[dict[str, Any]]
    report_sections: Optional[dict[str, str]]

    # ── Evaluation ────────────────────────────────────────────
    evaluation: Optional[dict[str, Any]]

    # ── Execution Tracking ────────────────────────────────────
    iteration: int
    agents_executed: Annotated[list[str], operator.add]
    tools_called: Annotated[list[str], operator.add]
    errors: Annotated[list[dict], operator.add]
    messages: Annotated[list[dict], operator.add]

    # ── Control Flow ──────────────────────────────────────────
    next_step: Optional[str]
    status: str
    # Status values: planning | researching | verifying | synthesizing | reporting | evaluating | complete | failed
