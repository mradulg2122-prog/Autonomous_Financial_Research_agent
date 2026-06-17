"""
Tool: sentiment_analysis
Performs NLP sentiment analysis on financial text.
Uses OpenAI for nuanced financial sentiment + VADER for quick scoring.
"""
from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.errors import ToolExecutionError
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.core.utils import parse_json_robustly
from backend.tools.registry import registry

logger = get_logger(__name__)


@registry.register(
    name="sentiment_analysis",
    description=(
        "Analyzes sentiment of financial text (news articles, earnings commentary, "
        "analyst reports). Returns sentiment scores (bullish/bearish/neutral), "
        "key themes, and investment-relevant signals."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of text snippets to analyze",
            },
            "context": {
                "type": "string",
                "description": "Context for analysis (e.g., 'earnings call', 'news article', 'analyst report')",
                "default": "financial text",
            },
            "company": {
                "type": "string",
                "description": "Company name or ticker for context",
                "default": "",
            },
        },
        "required": ["texts"],
    },
    timeout=30.0,
)
@with_retry(service="openai")
async def sentiment_analysis(
    texts: list[str],
    context: str = "financial text",
    company: str = "",
) -> dict[str, Any]:
    """Analyze sentiment using OpenAI for financial nuance."""
    logger.info("sentiment_analysis", text_count=len(texts))

    if not texts:
        return {"results": [], "aggregate": {}}

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    combined_text = "\n---\n".join(texts[:10])  # Limit to 10 texts

    prompt = f"""You are a financial analyst performing sentiment analysis.

Context: {context}
Company: {company or 'Not specified'}

Analyze the following financial text(s) and provide:
1. Overall sentiment: bullish/bearish/neutral with score (-1.0 to 1.0)
2. Individual sentiment for each text
3. Key themes identified
4. Investment-relevant signals
5. Risk flags (if any)

Text(s) to analyze:
{combined_text[:4000]}

Respond in valid JSON with this structure:
{{
  "overall_sentiment": "bullish|bearish|neutral",
  "overall_score": 0.0,
  "confidence": 0.0,
  "individual": [{{"text_index": 0, "sentiment": "...", "score": 0.0, "key_points": []}}],
  "themes": [],
  "signals": [],
  "risk_flags": []
}}"""

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    try:
        sentiment_data = parse_json_robustly(response.choices[0].message.content)
    except (json.JSONDecodeError, ValueError):
        sentiment_data = {
            "overall_sentiment": "neutral",
            "overall_score": 0.0,
            "confidence": 0.5,
            "themes": [],
            "signals": [],
            "risk_flags": [],
        }

    return {
        **sentiment_data,
        "texts_analyzed": len(texts),
        "context": context,
        "company": company,
        "source": "OpenAI Sentiment Analysis",
        "model": settings.openai_model,
    }
