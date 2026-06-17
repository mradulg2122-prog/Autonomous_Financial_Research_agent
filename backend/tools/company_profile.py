"""
Tool: company_profile
Retrieves comprehensive company profile and metadata.
"""
from __future__ import annotations

import asyncio
from typing import Any

import yfinance as yf

from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)


@registry.register(
    name="company_profile",
    description=(
        "Retrieves comprehensive company profile: business description, sector, industry, "
        "headquarters, employees, key executives, products/services, subsidiaries. "
        "Use this at the start of research to build foundational company context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Company stock ticker symbol",
            },
        },
        "required": ["ticker"],
    },
    timeout=20.0,
)
@with_retry(service="yfinance")
async def company_profile(ticker: str) -> dict[str, Any]:
    """Fetch comprehensive company profile."""
    logger.info("company_profile", ticker=ticker)

    loop = asyncio.get_event_loop()

    def _fetch():
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        # Get key executives
        try:
            executives = [
                {
                    "name": e.get("name"),
                    "title": e.get("title"),
                    "pay": e.get("totalPay"),
                }
                for e in (info.get("companyOfficers") or [])[:5]
            ]
        except Exception:
            executives = []

        # Institutional holders
        try:
            holders_df = stock.institutional_holders
            top_holders = (
                holders_df.head(5).to_dict("records")
                if holders_df is not None and not holders_df.empty
                else []
            )
        except Exception:
            top_holders = []

        return {
            "ticker": ticker,
            "company_name": info.get("longName", ticker),
            "short_name": info.get("shortName", ticker),
            "description": info.get("longBusinessSummary", "")[:2000],
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "sub_industry": info.get("industryDisp", ""),
            "country": info.get("country", ""),
            "city": info.get("city", ""),
            "state": info.get("state", ""),
            "website": info.get("website", ""),
            "full_time_employees": info.get("fullTimeEmployees"),
            "fiscal_year_end": info.get("fiscalYearEnd"),
            "exchange": info.get("exchange", ""),
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "float_shares": info.get("floatShares"),
            "phone": info.get("phone", ""),
            "address": info.get("address1", ""),
            "executives": executives,
            "top_institutional_holders": top_holders,
            "index_memberships": info.get("indexMemberships", []),
            "source": "Yahoo Finance Company Profile",
            "source_tier": 2,
        }

    return await loop.run_in_executor(None, _fetch)
