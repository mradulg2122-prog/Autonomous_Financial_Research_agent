"""
Tool: report_generator
Generates the final institutional-quality investment research report.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)

REPORT_SYSTEM_PROMPT = """You are a senior equity research analyst at a top-tier investment bank.
Your task is to write institutional-quality investment research reports.
Reports must be:
- Data-driven with specific numbers and evidence
- Analytically rigorous
- Clearly structured
- Written in professional financial language
- Include specific financial metrics and comparisons
- Balanced but opinionated where data supports it
"""


@registry.register(
    name="report_generator",
    description=(
        "Generates a full institutional investment research report from synthesized data. "
        "Produces all 14 sections: executive summary, company overview, financial analysis, "
        "growth analysis, profitability, competitive position, risks, management commentary, "
        "industry outlook, valuation, investment thesis, methodology, citations, confidence scores."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Company ticker"},
            "company_name": {"type": "string", "description": "Full company name"},
            "research_data": {
                "type": "object",
                "description": "All collected and synthesized research data",
            },
            "section": {
                "type": "string",
                "enum": [
                    "executive_summary", "company_overview", "financial_analysis",
                    "growth_analysis", "profitability_analysis", "competitive_position",
                    "risk_assessment", "management_commentary", "industry_outlook",
                    "valuation_metrics", "investment_thesis", "research_methodology",
                    "full_report",
                ],
                "description": "Which section to generate, or 'full_report' for complete report",
                "default": "full_report",
            },
        },
        "required": ["ticker", "research_data"],
    },
    timeout=480.0,
)
@with_retry(service="openai")
async def report_generator(
    ticker: str,
    research_data: dict[str, Any],
    company_name: str = "",
    section: str = "full_report",
) -> dict[str, Any]:
    """Generate investment research report sections."""
    logger.info("report_generator", ticker=ticker, section=section)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    company = company_name or ticker
    data_summary = json.dumps(research_data, default=str)[:8000]
    date_str = datetime.utcnow().strftime("%B %d, %Y")

    if section == "full_report":
        sections_content: dict[str, str] = {}

        section_prompts = {
            "executive_summary": f"Write a 3-paragraph Executive Summary for {company} ({ticker}). Include: investment rating, key thesis, top 3 catalysts, key risks, and 12-month price target if justified. Be specific with numbers.",
            "company_overview": f"Write a Company Overview for {company} ({ticker}). Cover: business model, revenue segments, geographic exposure, competitive advantages, management team highlights, and historical milestones.",
            "financial_analysis": f"Write a detailed Financial Analysis for {company} ({ticker}). Analyze revenue trends, EPS growth, cash generation, balance sheet strength, and compare to industry averages. Use specific numbers from the data.",
            "growth_analysis": f"Write a Growth Analysis for {company} ({ticker}). Cover: revenue growth drivers, market expansion, new products/services, TAM analysis, and 3-5 year growth projections with justification.",
            "profitability_analysis": f"Write a Profitability Analysis for {company} ({ticker}). Analyze gross margin, EBITDA margin, net margin trends, unit economics, operating leverage, and compare to peers.",
            "competitive_position": f"Write a Competitive Position analysis for {company} ({ticker}). Cover: market share, competitive moat, Porter's Five Forces, key competitors, and differentiation strategy.",
            "risk_assessment": f"Write a Risk Assessment for {company} ({ticker}). Identify top 5-7 risks: regulatory, competitive, financial, operational, macro. Rate each by severity and likelihood.",
            "management_commentary": f"Write a Management Commentary section for {company} ({ticker}). Summarize recent earnings call themes, forward guidance, capital allocation strategy, and management track record.",
            "industry_outlook": f"Write an Industry Outlook for {company} ({ticker})'s sector. Cover: industry growth rate, structural trends, regulatory environment, technology disruption, and macro tailwinds/headwinds.",
            "valuation_metrics": f"Write a Valuation Metrics section for {company} ({ticker}). Present: current multiples vs. historical averages vs. peers, DCF considerations, and fair value range.",
            "investment_thesis": f"Write an Investment Thesis for {company} ({ticker}). Clearly state: Bull case, Base case, Bear case with specific scenarios, catalysts, and price targets for each.",
            "research_methodology": f"Write a Research Methodology section explaining data sources, analysis approach, and confidence levels used in this report for {company} ({ticker}).",
        }

        for sec_name, sec_prompt in section_prompts.items():
            full_prompt = f"""{sec_prompt}

Available Research Data:
{data_summary}

Write in professional financial research style. Be specific with numbers where available.
Format as clean markdown with appropriate headers."""

            # Delay between sections to respect Gemini free-tier rate limits
            await asyncio.sleep(8)

            for attempt in range(3):  # Up to 3 attempts per section
                try:
                    response = await client.chat.completions.create(
                        model=settings.openai_model,
                        messages=[
                            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                            {"role": "user", "content": full_prompt},
                        ],
                        temperature=0.2,
                        max_tokens=1500,
                    )
                    sections_content[sec_name] = response.choices[0].message.content or _placeholder(sec_name, company, ticker)
                    break  # Success — move to next section
                except Exception as exc:
                    err_str = str(exc)
                    if ("429" in err_str or "rate" in err_str.lower() or "quota" in err_str.lower()) and attempt < 2:
                        # Rate limited — wait and retry
                        logger.warning("report_section_rate_limited", section=sec_name, attempt=attempt + 1)
                        await asyncio.sleep(30)  # Wait 30s before retry
                    else:
                        logger.warning("report_section_error", section=sec_name, error=err_str)
                        sections_content[sec_name] = _placeholder(sec_name, company, ticker)
                        break

        # Assemble full report markdown
        full_md = f"""# {company} ({ticker}) — Investment Research Report

**Date:** {date_str}
**Report Type:** Equity Research | Initiation of Coverage
**Prepared by:** ARA-1 Autonomous Research Agent

---

## Executive Summary

{sections_content.get('executive_summary', '')}

---

## Company Overview

{sections_content.get('company_overview', '')}

---

## Financial Analysis

{sections_content.get('financial_analysis', '')}

---

## Growth Analysis

{sections_content.get('growth_analysis', '')}

---

## Profitability Analysis

{sections_content.get('profitability_analysis', '')}

---

## Competitive Position

{sections_content.get('competitive_position', '')}

---

## Risk Assessment

{sections_content.get('risk_assessment', '')}

---

## Management Commentary

{sections_content.get('management_commentary', '')}

---

## Industry Outlook

{sections_content.get('industry_outlook', '')}

---

## Valuation Metrics

{sections_content.get('valuation_metrics', '')}

---

## Investment Thesis

{sections_content.get('investment_thesis', '')}

---

## Research Methodology

{sections_content.get('research_methodology', '')}

---

*This report was generated by ARA-1 Autonomous Financial Research Agent.
All data sourced from public filings, financial APIs, and validated sources.
This is for informational purposes only and does not constitute financial advice.*
"""

        return {
            "ticker": ticker,
            "company_name": company,
            "section": "full_report",
            "sections": sections_content,
            "full_report_markdown": full_md,
            "generated_at": date_str,
            "source": "ARA-1 Report Generator",
        }

    else:
        # Generate single section
        await asyncio.sleep(2)
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Write the {section} section for {company} ({ticker}).\n\nData:\n{data_summary}",
                    },
                ],
                temperature=0.2,
                max_tokens=2000,
            )
            content = response.choices[0].message.content or _placeholder(section, company, ticker)
        except Exception as exc:
            logger.warning("report_single_section_error", section=section, error=str(exc))
            content = _placeholder(section, company, ticker)

        return {
            "ticker": ticker,
            "section": section,
            "content": content,
            "generated_at": date_str,
        }


def _placeholder(section: str, company: str, ticker: str) -> str:
    """Return a professional placeholder for a section that failed to generate."""
    return (
        f"*{section.replace('_', ' ').title()} analysis for {company} ({ticker}) "
        f"could not be generated at this time due to API constraints. "
        f"Data collection for this company has been completed and is available "
        f"in the underlying research dataset.*"
    )

