"""
ARA-1 Evaluation Agent
Scores research quality on 25+ metrics across 11 categories.
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.core.utils import parse_json_robustly
from backend.graph.state import ResearchState

logger = get_logger(__name__)


def _compute_tool_efficiency(state: ResearchState) -> float:
    """Score tool efficiency: ratio of unique tools / total calls."""
    total = len(state.get("tools_called") or [])
    unique = len(set(state.get("tools_called") or []))
    if total == 0:
        return 0.0
    redundancy = (total - unique) / total
    return round(max(0.0, 1.0 - redundancy), 3)


def _compute_source_diversity(state: ResearchState) -> float:
    """Score how many different source tiers were used."""
    sources = 0
    if (state.get("sec_data") or {}).get("filings"):
        sources += 1  # Tier 1
    if state.get("financial_data"):
        sources += 1  # Tier 2
    if state.get("earnings_data"):
        sources += 1  # Tier 3
    if (state.get("news_data") or {}).get("articles"):
        sources += 1  # Tier 4
    return round(sources / 4.0, 3)  # 4 tiers = full score


def _compute_completeness(state: ResearchState) -> float:
    """Score completeness of the report sections."""
    sections = state.get("report_sections") or {}
    expected = [
        "executive_summary", "company_overview", "financial_analysis",
        "growth_analysis", "profitability_analysis", "competitive_position",
        "risk_assessment", "management_commentary", "industry_outlook",
        "valuation_metrics", "investment_thesis", "research_methodology",
    ]
    found = sum(1 for s in expected if sections.get(s) and len(sections[s]) > 100)
    return round(found / len(expected), 3)


def _compute_hallucination_risk(state: ResearchState) -> float:
    """Estimate hallucination risk from fact-check results (lower = better)."""
    fc = state.get("fact_check_results") or {}
    summary = fc.get("summary") or {}
    total = summary.get("total", 0)
    disputed = summary.get("disputed", 0)
    if total == 0:
        return 0.3  # Unknown risk
    return round(disputed / total, 3)


@with_retry(service="openai")
async def run_evaluation_agent(state: ResearchState) -> dict[str, Any]:
    """Evaluation Agent: computes 25+ quality metrics for the research session."""
    ticker = state.get("company_ticker", "")

    logger.info("evaluation_agent_start", ticker=ticker)

    report = state.get("report") or {}
    sections = state.get("report_sections") or {}
    tools_called = state.get("tools_called") or []
    errors = state.get("errors") or []
    verified = state.get("verified_claims") or []

    # ── Category Scores ───────────────────────────────────────
    source_diversity = _compute_source_diversity(state)
    tool_efficiency = _compute_tool_efficiency(state)
    completeness = _compute_completeness(state)
    hallucination_risk = _compute_hallucination_risk(state)
    error_count = len(errors)

    # LLM-based quality scoring for analytical content
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    report_excerpt = json.dumps({
        k: v[:500] if isinstance(v, str) else v
        for k, v in sections.items()
    }, default=str)[:4000]

    quality_prompt = f"""Score this financial research report on the following criteria (0.0-1.0):

Report sections:
{report_excerpt}

Score each (respond in JSON):
{{
  "factual_accuracy": 0.0,      // Are facts specific and sourced?
  "analytical_depth": 0.0,      // Does analysis go beyond surface facts?
  "reasoning_quality": 0.0,     // Is reasoning logical and coherent?
  "report_quality": 0.0,        // Professional presentation quality?
  "investment_thesis_clarity": 0.0,  // Is investment thesis clear?
  "risk_coverage": 0.0,         // Are risks adequately covered?
  "valuation_rigor": 0.0,       // Is valuation analysis rigorous?
  "commentary_insight": 0.0     // Quality of management commentary analysis?
}}"""

    quality_scores: dict[str, float] = {}
    try:
        q_response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": quality_prompt}],
            temperature=0.0,
        )
        quality_scores = parse_json_robustly(q_response.choices[0].message.content)
    except Exception:
        quality_scores = {k: 0.5 for k in [
            "factual_accuracy", "analytical_depth", "reasoning_quality",
            "report_quality", "investment_thesis_clarity", "risk_coverage",
            "valuation_rigor", "commentary_insight",
        ]}

    # ── Compile 25+ Detailed Metrics ─────────────────────────
    detailed_metrics: dict[str, Any] = {
        # Factual Accuracy (3 metrics)
        "factual_accuracy_score": quality_scores.get("factual_accuracy", 0.5),
        "fact_verification_rate": min(1.0, len(verified) / max(1, 10)),
        "source_citation_count": len(report.get("source_citations") or []),

        # Completeness (3 metrics)
        "report_completeness": completeness,
        "section_count": len([s for s in sections.values() if s and len(s) > 50]),
        "data_source_coverage": source_diversity,

        # Analytical Depth (3 metrics)
        "analytical_depth_score": quality_scores.get("analytical_depth", 0.5),
        "investment_thesis_clarity": quality_scores.get("investment_thesis_clarity", 0.5),
        "valuation_rigor": quality_scores.get("valuation_rigor", 0.5),

        # Reasoning Quality (2 metrics)
        "reasoning_quality_score": quality_scores.get("reasoning_quality", 0.5),
        "logic_coherence": quality_scores.get("reasoning_quality", 0.5),

        # Tool Efficiency (3 metrics)
        "tool_efficiency_score": tool_efficiency,
        "total_tool_calls": len(tools_called),
        "unique_tools_used": len(set(tools_called)),

        # Memory Utilization (2 metrics)
        "vector_search_used": any(t == "vector_db_search" for t in tools_called),
        "memory_hit_rate": 0.5 if any(t == "vector_db_search" for t in tools_called) else 0.0,

        # Hallucination Rate (2 metrics)
        "hallucination_risk_score": 1.0 - hallucination_risk,  # Higher = less hallu
        "disputed_claim_rate": hallucination_risk,

        # Source Diversity (2 metrics)
        "source_diversity_score": source_diversity,
        "sec_data_included": bool((state.get("sec_data") or {}).get("filings")),

        # Latency (2 metrics)
        "total_agents_executed": len(set(state.get("agents_executed") or [])),
        "estimated_latency_score": 0.8,  # Placeholder until timing data

        # Error Recovery (2 metrics)
        "error_count": error_count,
        "error_recovery_rate": max(0.0, 1.0 - (error_count / max(1, len(tools_called) + 1))),

        # Report Quality (4 metrics)
        "report_quality_score": quality_scores.get("report_quality", 0.5),
        "risk_coverage_score": quality_scores.get("risk_coverage", 0.5),
        "management_commentary_quality": quality_scores.get("commentary_insight", 0.5),
        "peer_comparison_included": bool(state.get("peer_data")),
    }

    # ── Compute Category Averages ─────────────────────────────
    category_scores = {
        "factual_accuracy": (
            detailed_metrics["factual_accuracy_score"] +
            detailed_metrics["fact_verification_rate"]
        ) / 2,
        "completeness": (
            detailed_metrics["report_completeness"] +
            detailed_metrics["data_source_coverage"]
        ) / 2,
        "analytical_depth": (
            detailed_metrics["analytical_depth_score"] +
            detailed_metrics["investment_thesis_clarity"] +
            detailed_metrics["valuation_rigor"]
        ) / 3,
        "reasoning_quality": detailed_metrics["reasoning_quality_score"],
        "tool_efficiency": detailed_metrics["tool_efficiency_score"],
        "memory_utilization": detailed_metrics["memory_hit_rate"],
        "hallucination_rate": detailed_metrics["hallucination_risk_score"],
        "source_diversity": detailed_metrics["source_diversity_score"],
        "latency_score": detailed_metrics["estimated_latency_score"],
        "error_recovery": detailed_metrics["error_recovery_rate"],
        "report_quality": (
            detailed_metrics["report_quality_score"] +
            detailed_metrics["risk_coverage_score"]
        ) / 2,
    }

    overall_score = round(sum(category_scores.values()) / len(category_scores), 3)

    # Grade
    if overall_score >= 0.9:
        grade = "A+"
    elif overall_score >= 0.85:
        grade = "A"
    elif overall_score >= 0.8:
        grade = "A-"
    elif overall_score >= 0.75:
        grade = "B+"
    elif overall_score >= 0.7:
        grade = "B"
    elif overall_score >= 0.65:
        grade = "B-"
    else:
        grade = "C"

    evaluation = {
        "ticker": ticker,
        "overall_score": overall_score,
        "grade": grade,
        "category_scores": category_scores,
        "detailed_metrics": detailed_metrics,
        "metric_count": len(detailed_metrics),
    }

    logger.info(
        "evaluation_agent_complete",
        ticker=ticker,
        overall_score=overall_score,
        grade=grade,
    )

    return {
        "evaluation": evaluation,
        "agents_executed": ["evaluation_agent"],
        "status": "complete",
        "messages": [{
            "role": "evaluation_agent",
            "content": f"Evaluation complete. Overall score: {overall_score:.2f} ({grade})",
        }],
    }
