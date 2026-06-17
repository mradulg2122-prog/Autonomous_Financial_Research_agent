"""
ARA-1 Conflict Resolver
Resolves data conflicts using a 5-tier source hierarchy.

Tier 1: SEC Filings (highest authority)
Tier 2: Financial APIs (yfinance, Alpha Vantage)
Tier 3: Earnings Calls
Tier 4: Major News Sources
Tier 5: Web Search (lowest authority)
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from backend.core.logging import get_logger

logger = get_logger(__name__)

SOURCE_TIERS: dict[str, int] = {
    "SEC EDGAR": 1,
    "sec_filing": 1,
    "Yahoo Finance": 2,
    "Alpha Vantage": 2,
    "financial_api": 2,
    "Earnings Data": 3,
    "earnings_transcript": 3,
    "NewsAPI": 4,
    "Reuters": 4,
    "Bloomberg": 4,
    "major_news": 4,
    "DuckDuckGo": 5,
    "web_search": 5,
}


def _get_tier(source: str) -> int:
    """Get source tier — lower = more authoritative."""
    for key, tier in SOURCE_TIERS.items():
        if key.lower() in source.lower():
            return tier
    return 5  # Default to lowest


class ConflictResolver:
    """
    Resolves conflicts between data from different sources.
    Resolution strategy:
    1. Compare source tiers → prefer lower tier (more authoritative)
    2. If same tier: prefer more recent timestamp
    3. If same tier and timestamp: prefer higher confidence score
    4. Log all resolutions for audit trail
    """

    def __init__(self) -> None:
        self.resolutions: list[dict[str, Any]] = []

    def resolve(
        self,
        field: str,
        value_a: Any,
        source_a: str,
        value_b: Any,
        source_b: str,
        timestamp_a: Optional[str] = None,
        timestamp_b: Optional[str] = None,
        confidence_a: float = 0.5,
        confidence_b: float = 0.5,
    ) -> dict[str, Any]:
        """
        Resolve a conflict between two values from different sources.
        Returns resolution dict with chosen value and rationale.
        """
        tier_a = _get_tier(source_a)
        tier_b = _get_tier(source_b)

        # Step 1: Source tier comparison
        if tier_a < tier_b:
            winner = "a"
            rationale = f"Source tier: {source_a} (Tier {tier_a}) > {source_b} (Tier {tier_b})"
        elif tier_b < tier_a:
            winner = "b"
            rationale = f"Source tier: {source_b} (Tier {tier_b}) > {source_a} (Tier {tier_a})"
        else:
            # Step 2: Timestamp comparison
            try:
                ts_a = datetime.fromisoformat(timestamp_a) if timestamp_a else datetime.min
                ts_b = datetime.fromisoformat(timestamp_b) if timestamp_b else datetime.min
                if ts_a > ts_b:
                    winner = "a"
                    rationale = f"More recent timestamp: {timestamp_a}"
                elif ts_b > ts_a:
                    winner = "b"
                    rationale = f"More recent timestamp: {timestamp_b}"
                else:
                    # Step 3: Confidence score
                    if confidence_a >= confidence_b:
                        winner = "a"
                        rationale = f"Higher confidence score: {confidence_a:.2f}"
                    else:
                        winner = "b"
                        rationale = f"Higher confidence score: {confidence_b:.2f}"
            except Exception:
                winner = "a" if confidence_a >= confidence_b else "b"
                rationale = "Confidence-based resolution (timestamp parse failed)"

        chosen_value = value_a if winner == "a" else value_b
        chosen_source = source_a if winner == "a" else source_b
        rejected_value = value_b if winner == "a" else value_a
        rejected_source = source_b if winner == "a" else source_a

        resolution = {
            "field": field,
            "chosen_value": chosen_value,
            "chosen_source": chosen_source,
            "chosen_tier": _get_tier(chosen_source),
            "rejected_value": rejected_value,
            "rejected_source": rejected_source,
            "rejected_tier": _get_tier(rejected_source),
            "rationale": rationale,
            "resolved_at": datetime.utcnow().isoformat(),
        }

        self.resolutions.append(resolution)
        logger.info(
            "conflict_resolved",
            field=field,
            chosen_source=chosen_source,
            rationale=rationale,
        )

        return resolution

    def resolve_batch(
        self, conflicts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Resolve a batch of conflicts."""
        results = []
        for conflict in conflicts:
            resolution = self.resolve(
                field=conflict.get("field", "unknown"),
                value_a=conflict.get("value_a"),
                source_a=conflict.get("source_a", "unknown"),
                value_b=conflict.get("value_b"),
                source_b=conflict.get("source_b", "unknown"),
                timestamp_a=conflict.get("timestamp_a"),
                timestamp_b=conflict.get("timestamp_b"),
                confidence_a=conflict.get("confidence_a", 0.5),
                confidence_b=conflict.get("confidence_b", 0.5),
            )
            results.append(resolution)
        return results

    def get_resolutions(self) -> list[dict[str, Any]]:
        return self.resolutions

    def get_audit_log(self) -> str:
        return json.dumps(self.resolutions, indent=2, default=str)
