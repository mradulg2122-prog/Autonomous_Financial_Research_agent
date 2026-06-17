"""
Tool: risk_analysis_tool
Extracts and scores risk factors from SEC filings, news, and market data.
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


@registry.register(
    name="risk_analysis_tool",
    description=(
        "Analyzes and scores risk factors for a company. Identifies: regulatory risks, "
        "competitive risks, financial risks, operational risks, macro risks. "
        "Assigns severity scores and produces a risk matrix. Use after collecting "
        "SEC filings, news, and financial data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Company ticker symbol",
            },
            "risk_data": {
                "type": "object",
                "description": "Compiled risk data from SEC filings, news, financial analysis",
                "default": {},
            },
            "context": {
                "type": "string",
                "description": "Additional context about the company and industry",
                "default": "",
            },
        },
        "required": ["ticker"],
    },
    timeout=30.0,
)
@with_retry(service="openai")
async def risk_analysis_tool(
    ticker: str,
    risk_data: dict[str, Any] = None,
    context: str = "",
) -> dict[str, Any]:
    """Analyze and score company risk factors using LLM."""
    logger.info("risk_analysis_tool", ticker=ticker)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    data_summary = json.dumps(risk_data or {}, default=str)[:3000]

    prompt = f"""You are a senior financial risk analyst. Analyze the risks for {ticker}.

Context: {context}

Available Data:
{data_summary}

Perform a comprehensive risk analysis. Identify and score risks in these categories:
1. Financial Risk (leverage, liquidity, credit)
2. Regulatory/Legal Risk (compliance, litigation)
3. Competitive Risk (market share, disruption)
4. Operational Risk (supply chain, technology, management)
5. Macroeconomic Risk (interest rates, recession, geopolitics)
6. ESG Risk (environmental, social, governance)

For each risk, provide:
- Risk name
- Description
- Severity (1-5, where 5=critical)
- Likelihood (1-5)
- Risk score (severity × likelihood)
- Mitigation strategies

Return valid JSON:
{{
  "ticker": "{ticker}",
  "risk_matrix": [
    {{
      "category": "Financial Risk",
      "risks": [
        {{
          "name": "...",
          "description": "...",
          "severity": 3,
          "likelihood": 3,
          "risk_score": 9,
          "mitigations": []
        }}
      ]
    }}
  ],
  "top_risks": ["...", "..."],
  "overall_risk_rating": "Low|Medium|High|Very High",
  "overall_risk_score": 0.0,
  "investment_implications": "..."
}}"""

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    try:
        risk_result = parse_json_robustly(response.choices[0].message.content)
    except (json.JSONDecodeError, ValueError):
        risk_result = {
            "ticker": ticker,
            "risk_matrix": [],
            "top_risks": ["Data parsing error — manual review required"],
            "overall_risk_rating": "Unknown",
            "overall_risk_score": 0.0,
            "investment_implications": "Risk analysis could not be completed.",
        }

    return {
        **risk_result,
        "source": "ARA-1 Risk Analysis Engine",
    }
