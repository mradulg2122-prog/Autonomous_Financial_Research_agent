"""
ARA-1 Automated Benchmark Suite
8 challenge scenarios for testing research quality.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from backend.core.logging import get_logger

logger = get_logger(__name__)

BENCHMARK_CHALLENGES = [
    {
        "id": 1,
        "name": "Company Profile",
        "description": "Retrieve comprehensive company profile",
        "query": "Give me a complete profile of Apple Inc including business model, segments, and competitive advantages",
        "ticker": "AAPL",
        "expected_sections": ["company_overview", "competitive_position"],
        "min_score": 0.7,
    },
    {
        "id": 2,
        "name": "Financial Summary",
        "description": "Generate a financial data summary with key metrics",
        "query": "Analyze Microsoft's financial performance: revenue trends, margins, and key ratios",
        "ticker": "MSFT",
        "expected_sections": ["financial_analysis", "profitability_analysis"],
        "min_score": 0.75,
    },
    {
        "id": 3,
        "name": "Risk Assessment",
        "description": "Identify and score company risk factors",
        "query": "Perform a comprehensive risk assessment for Tesla including regulatory, competitive, and financial risks",
        "ticker": "TSLA",
        "expected_sections": ["risk_assessment"],
        "min_score": 0.70,
    },
    {
        "id": 4,
        "name": "Peer Comparison",
        "description": "Compare company against industry peers",
        "query": "Compare Google (Alphabet) against its technology peers on valuation and profitability metrics",
        "ticker": "GOOGL",
        "expected_sections": ["competitive_position"],
        "min_score": 0.70,
    },
    {
        "id": 5,
        "name": "Earnings Analysis",
        "description": "Analyze earnings trajectory and guidance",
        "query": "Analyze Amazon's recent earnings: performance vs expectations, guidance, and key management commentary",
        "ticker": "AMZN",
        "expected_sections": ["management_commentary", "growth_analysis"],
        "min_score": 0.65,
    },
    {
        "id": 6,
        "name": "Industry Research",
        "description": "Research industry trends and outlook",
        "query": "Research the semiconductor industry: key trends, leading companies, and outlook for next 2 years",
        "ticker": "NVDA",
        "expected_sections": ["industry_outlook", "competitive_position"],
        "min_score": 0.70,
    },
    {
        "id": 7,
        "name": "Investment Thesis",
        "description": "Generate bull, base, and bear case investment thesis",
        "query": "Develop a full investment thesis for JPMorgan Chase with bull, base, and bear cases",
        "ticker": "JPM",
        "expected_sections": ["investment_thesis", "valuation_metrics"],
        "min_score": 0.75,
    },
    {
        "id": 8,
        "name": "Full Institutional Research Report",
        "description": "Generate a complete 14-section investment research report",
        "query": "Generate a comprehensive institutional investment research report for Nvidia covering all aspects",
        "ticker": "NVDA",
        "expected_sections": [
            "executive_summary", "company_overview", "financial_analysis",
            "risk_assessment", "investment_thesis", "valuation_metrics",
        ],
        "min_score": 0.80,
    },
]


async def run_benchmark(challenge: dict[str, Any]) -> dict[str, Any]:
    """Run a single benchmark challenge."""
    from backend.graph.state import ResearchState
    from backend.graph.workflow import get_compiled_graph
    import uuid

    logger.info(
        "benchmark_start",
        challenge_id=challenge["id"],
        name=challenge["name"],
    )

    start_time = datetime.utcnow()
    session_id = str(uuid.uuid4())

    initial_state: ResearchState = {
        "session_id": session_id,
        "query": challenge["query"],
        "company_ticker": challenge["ticker"],
        "company_name": "",
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

    try:
        graph = get_compiled_graph()
        final_state = await graph.ainvoke(initial_state)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Check expected sections
        sections = final_state.get("report_sections") or {}
        sections_found = [
            s for s in challenge["expected_sections"]
            if sections.get(s) and len(sections[s]) > 100
        ]
        section_coverage = len(sections_found) / max(1, len(challenge["expected_sections"]))

        eval_score = (final_state.get("evaluation") or {}).get("overall_score", 0.0)
        passed = eval_score >= challenge["min_score"] and section_coverage >= 0.75

        result = {
            "challenge_id": challenge["id"],
            "name": challenge["name"],
            "ticker": challenge["ticker"],
            "session_id": session_id,
            "passed": passed,
            "eval_score": eval_score,
            "min_score": challenge["min_score"],
            "section_coverage": section_coverage,
            "sections_found": sections_found,
            "duration_seconds": duration,
            "error": None,
        }

        logger.info(
            "benchmark_complete",
            challenge_id=challenge["id"],
            passed=passed,
            score=eval_score,
        )
        return result

    except Exception as exc:
        logger.error("benchmark_error", challenge_id=challenge["id"], error=str(exc))
        return {
            "challenge_id": challenge["id"],
            "name": challenge["name"],
            "ticker": challenge["ticker"],
            "session_id": session_id,
            "passed": False,
            "eval_score": 0.0,
            "error": str(exc),
        }


async def run_all_benchmarks() -> dict[str, Any]:
    """Run all 8 benchmark challenges sequentially."""
    logger.info("benchmark_suite_start", total=len(BENCHMARK_CHALLENGES))

    results = []
    for challenge in BENCHMARK_CHALLENGES:
        result = await run_benchmark(challenge)
        results.append(result)
        await asyncio.sleep(2)  # Brief pause between benchmarks

    passed = sum(1 for r in results if r.get("passed"))
    avg_score = sum(r.get("eval_score", 0) for r in results) / len(results)

    summary = {
        "total_challenges": len(BENCHMARK_CHALLENGES),
        "passed": passed,
        "failed": len(BENCHMARK_CHALLENGES) - passed,
        "pass_rate": passed / len(BENCHMARK_CHALLENGES),
        "average_score": round(avg_score, 3),
        "results": results,
        "run_at": datetime.utcnow().isoformat(),
    }

    logger.info(
        "benchmark_suite_complete",
        passed=passed,
        total=len(BENCHMARK_CHALLENGES),
        avg_score=avg_score,
    )

    return summary
