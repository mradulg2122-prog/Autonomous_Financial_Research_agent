"""
ARA-1 Evaluation Metrics
25+ metrics across 11 categories with detailed scoring rubrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class MetricCategory(str, Enum):
    FACTUAL_ACCURACY = "factual_accuracy"
    COMPLETENESS = "completeness"
    ANALYTICAL_DEPTH = "analytical_depth"
    REASONING_QUALITY = "reasoning_quality"
    TOOL_EFFICIENCY = "tool_efficiency"
    MEMORY_UTILIZATION = "memory_utilization"
    HALLUCINATION_RATE = "hallucination_rate"
    SOURCE_DIVERSITY = "source_diversity"
    LATENCY = "latency"
    ERROR_RECOVERY = "error_recovery"
    REPORT_QUALITY = "report_quality"


@dataclass
class Metric:
    """A single evaluation metric definition."""
    name: str
    category: MetricCategory
    description: str
    min_value: float = 0.0
    max_value: float = 1.0
    higher_is_better: bool = True
    weight: float = 1.0


@dataclass
class MetricResult:
    """Computed result for a single metric."""
    metric: Metric
    value: float
    raw_value: Any = None
    explanation: str = ""

    @property
    def normalized_value(self) -> float:
        """Normalize value to [0, 1] range."""
        span = self.metric.max_value - self.metric.min_value
        if span == 0:
            return 0.0
        v = (self.value - self.metric.min_value) / span
        return max(0.0, min(1.0, v))

    @property
    def score(self) -> float:
        """Weighted score contribution."""
        v = self.normalized_value
        return (v if self.metric.higher_is_better else 1.0 - v) * self.metric.weight


# ── Metric Definitions ────────────────────────────────────────

METRICS: list[Metric] = [
    # ── Factual Accuracy (3 metrics) ──────────────────────────
    Metric("factual_accuracy_score", MetricCategory.FACTUAL_ACCURACY,
           "LLM-assessed accuracy of financial facts", weight=2.0),
    Metric("fact_verification_rate", MetricCategory.FACTUAL_ACCURACY,
           "Fraction of claims successfully verified against source data", weight=2.0),
    Metric("source_citation_count", MetricCategory.FACTUAL_ACCURACY,
           "Number of distinct sources cited in the report",
           min_value=0, max_value=10, weight=0.5),

    # ── Completeness (3 metrics) ───────────────────────────────
    Metric("report_completeness", MetricCategory.COMPLETENESS,
           "Fraction of 12 expected report sections present and non-trivial", weight=2.0),
    Metric("section_count", MetricCategory.COMPLETENESS,
           "Total sections with meaningful content (>100 chars)",
           min_value=0, max_value=14, weight=0.5),
    Metric("data_source_coverage", MetricCategory.COMPLETENESS,
           "Number of data source tiers used (SEC/Financial/Earnings/News)",
           min_value=0, max_value=4, weight=1.0),

    # ── Analytical Depth (3 metrics) ──────────────────────────
    Metric("analytical_depth_score", MetricCategory.ANALYTICAL_DEPTH,
           "LLM-assessed depth of analysis beyond surface facts", weight=2.0),
    Metric("investment_thesis_clarity", MetricCategory.ANALYTICAL_DEPTH,
           "Clarity and specificity of the investment thesis", weight=1.5),
    Metric("valuation_rigor", MetricCategory.ANALYTICAL_DEPTH,
           "Use of appropriate valuation multiples and comparisons", weight=1.5),

    # ── Reasoning Quality (2 metrics) ─────────────────────────
    Metric("reasoning_quality_score", MetricCategory.REASONING_QUALITY,
           "LLM-assessed quality of analytical reasoning", weight=2.0),
    Metric("logic_coherence", MetricCategory.REASONING_QUALITY,
           "Internal consistency of arguments and conclusions", weight=1.5),

    # ── Tool Efficiency (3 metrics) ───────────────────────────
    Metric("tool_efficiency_score", MetricCategory.TOOL_EFFICIENCY,
           "Ratio of unique tools / total calls (low redundancy = high score)", weight=1.0),
    Metric("total_tool_calls", MetricCategory.TOOL_EFFICIENCY,
           "Total number of tool invocations",
           min_value=0, max_value=50, higher_is_better=False, weight=0.3),
    Metric("unique_tools_used", MetricCategory.TOOL_EFFICIENCY,
           "Number of distinct tools used across the session",
           min_value=0, max_value=15, weight=0.7),

    # ── Memory Utilization (2 metrics) ────────────────────────
    Metric("vector_search_used", MetricCategory.MEMORY_UTILIZATION,
           "Whether vector DB search was used for context retrieval",
           min_value=0, max_value=1, weight=0.5),
    Metric("memory_hit_rate", MetricCategory.MEMORY_UTILIZATION,
           "Rate at which previously stored knowledge was retrieved", weight=1.0),

    # ── Hallucination Rate (2 metrics) ────────────────────────
    Metric("hallucination_risk_score", MetricCategory.HALLUCINATION_RATE,
           "Inverse of disputed claim rate (higher = fewer disputed claims)", weight=2.0),
    Metric("disputed_claim_rate", MetricCategory.HALLUCINATION_RATE,
           "Fraction of claims marked as disputed or unverifiable",
           higher_is_better=False, weight=2.0),

    # ── Source Diversity (2 metrics) ──────────────────────────
    Metric("source_diversity_score", MetricCategory.SOURCE_DIVERSITY,
           "Normalized number of source tiers used", weight=1.5),
    Metric("sec_data_included", MetricCategory.SOURCE_DIVERSITY,
           "Whether primary SEC filing data (Tier 1) was included",
           min_value=0, max_value=1, weight=1.0),

    # ── Latency (2 metrics) ───────────────────────────────────
    Metric("total_agents_executed", MetricCategory.LATENCY,
           "Number of distinct agents that completed execution",
           min_value=0, max_value=9, weight=0.5),
    Metric("estimated_latency_score", MetricCategory.LATENCY,
           "Inverse score for total execution time (faster = higher)", weight=0.5),

    # ── Error Recovery (2 metrics) ────────────────────────────
    Metric("error_count", MetricCategory.ERROR_RECOVERY,
           "Total number of errors encountered during execution",
           min_value=0, max_value=20, higher_is_better=False, weight=1.0),
    Metric("error_recovery_rate", MetricCategory.ERROR_RECOVERY,
           "Fraction of errors that did not halt execution", weight=1.5),

    # ── Report Quality (4 metrics) ────────────────────────────
    Metric("report_quality_score", MetricCategory.REPORT_QUALITY,
           "LLM-assessed overall writing and presentation quality", weight=2.0),
    Metric("risk_coverage_score", MetricCategory.REPORT_QUALITY,
           "Adequacy of risk identification and analysis", weight=1.5),
    Metric("management_commentary_quality", MetricCategory.REPORT_QUALITY,
           "Quality of management commentary interpretation", weight=1.0),
    Metric("peer_comparison_included", MetricCategory.REPORT_QUALITY,
           "Whether peer comparison analysis was performed",
           min_value=0, max_value=1, weight=0.5),
]

# Metric lookup by name
METRIC_MAP: dict[str, Metric] = {m.name: m for m in METRICS}


def get_metric_names() -> list[str]:
    """Return all 25+ metric names."""
    return [m.name for m in METRICS]


def get_metrics_by_category(category: MetricCategory) -> list[Metric]:
    """Return all metrics in a given category."""
    return [m for m in METRICS if m.category == category]


def compute_category_averages(
    detailed_metrics: dict[str, Any]
) -> dict[str, float]:
    """
    Compute per-category average scores from detailed metric values.
    Returns dict of category_name -> average_score (0.0-1.0).
    """
    category_totals: dict[str, list[float]] = {}

    for metric in METRICS:
        raw = detailed_metrics.get(metric.name)
        if raw is None:
            continue

        try:
            value = float(raw) if not isinstance(raw, bool) else float(int(raw))
        except (TypeError, ValueError):
            continue

        # Normalize
        span = metric.max_value - metric.min_value
        if span == 0:
            continue
        normalized = max(0.0, min(1.0, (value - metric.min_value) / span))
        score = normalized if metric.higher_is_better else 1.0 - normalized

        cat = metric.category.value
        if cat not in category_totals:
            category_totals[cat] = []
        category_totals[cat].append(score * metric.weight)

    result: dict[str, float] = {}
    for category in MetricCategory:
        scores = category_totals.get(category.value, [])
        if scores:
            total_weight = sum(
                m.weight for m in METRICS
                if m.category == category and detailed_metrics.get(m.name) is not None
            )
            result[category.value] = round(sum(scores) / max(total_weight, 1.0), 3)
        else:
            result[category.value] = 0.0

    return result


def compute_overall_score(category_scores: dict[str, float]) -> float:
    """Compute weighted overall score from category scores."""
    if not category_scores:
        return 0.0
    return round(sum(category_scores.values()) / len(category_scores), 3)


def score_to_grade(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 0.93: return "A+"
    if score >= 0.90: return "A"
    if score >= 0.87: return "A-"
    if score >= 0.83: return "B+"
    if score >= 0.80: return "B"
    if score >= 0.77: return "B-"
    if score >= 0.73: return "C+"
    if score >= 0.70: return "C"
    if score >= 0.67: return "C-"
    if score >= 0.60: return "D"
    return "F"
