"""
Tool: fact_checker
Verifies numerical claims against source data and assigns confidence scores.
"""
from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.core.utils import parse_json_robustly
from backend.tools.registry import registry

logger = get_logger(__name__)


def _extract_numbers(text: str) -> list[dict[str, Any]]:
    """Extract numerical claims from text."""
    patterns = [
        # Dollar amounts
        (r"\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion|B|M|T))?", "currency"),
        # Percentages
        (r"[\d,]+(?:\.\d+)?\s*%", "percentage"),
        # Plain numbers with context
        (r"\b[\d,]+(?:\.\d+)?\s*(?:billion|million|trillion)\b", "large_number"),
    ]
    results = []
    for pattern, num_type in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            results.append({
                "value": match.group(),
                "type": num_type,
                "position": match.start(),
                "context": text[max(0, match.start() - 50):match.end() + 50],
            })
    return results[:20]  # Limit


@registry.register(
    name="fact_checker",
    description=(
        "Verifies factual claims (especially numerical/financial) in research text. "
        "Cross-references against provided source data and assigns confidence scores. "
        "Use this after collecting data to validate all claims before report generation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of claims to verify",
            },
            "source_data": {
                "type": "object",
                "description": "Source data dict to verify against (e.g., financial metrics)",
                "default": {},
            },
            "context": {
                "type": "string",
                "description": "Research context (company name, topic)",
                "default": "",
            },
        },
        "required": ["claims"],
    },
    timeout=30.0,
)
@with_retry(service="openai")
async def fact_checker(
    claims: list[str],
    source_data: dict[str, Any] = None,
    context: str = "",
) -> dict[str, Any]:
    """Verify claims using source data and LLM cross-checking."""
    logger.info("fact_checker", claim_count=len(claims))

    if not claims:
        return {"verified": [], "summary": {"total": 0, "verified": 0, "disputed": 0}}

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    source_summary = json.dumps(source_data or {}, default=str)[:3000]

    prompt = f"""You are a financial fact-checker. Verify the following claims.

Context: {context}

Available Source Data:
{source_summary}

Claims to verify:
{json.dumps(claims, indent=2)}

For each claim, determine:
1. Whether it's verifiable against the source data
2. A confidence score (0.0-1.0)
3. Status: verified | disputed | unverifiable | partially_verified
4. Any corrections if the claim appears wrong
5. The supporting evidence

Return valid JSON:
{{
  "verified_claims": [
    {{
      "claim": "...",
      "status": "verified|disputed|unverifiable|partially_verified",
      "confidence": 0.0,
      "evidence": "...",
      "correction": null
    }}
  ],
  "summary": {{
    "total": 0,
    "verified": 0,
    "disputed": 0,
    "unverifiable": 0,
    "average_confidence": 0.0
  }}
}}"""

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    try:
        result = parse_json_robustly(response.choices[0].message.content)
    except (json.JSONDecodeError, ValueError):
        result = {
            "verified_claims": [
                {"claim": c, "status": "unverifiable", "confidence": 0.5, "evidence": "Parse error"}
                for c in claims
            ],
            "summary": {
                "total": len(claims),
                "verified": 0,
                "disputed": 0,
                "unverifiable": len(claims),
                "average_confidence": 0.5,
            },
        }

    return {
        **result,
        "context": context,
        "source": "LLM Fact Verification",
    }
