"""
Tool: financial_data_api
Retrieves financial metrics: revenue, profitability, ratios, cash flow.
Primary source: yfinance. Fallback: Alpha Vantage.
"""
from __future__ import annotations

from typing import Any, Optional

import yfinance as yf

from backend.core.config import settings
from backend.core.errors import ToolExecutionError
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)


def _safe(val: Any, default: Any = None) -> Any:
    """Return default if val is None or NaN."""
    import math
    if val is None:
        return default
    try:
        if isinstance(val, float) and math.isnan(val):
            return default
    except Exception:
        pass
    return val


@registry.register(
    name="financial_data_api",
    description=(
        "Retrieves comprehensive financial data for a company: income statement, "
        "balance sheet, cash flow statement, key ratios (P/E, EV/EBITDA, ROE, etc.), "
        "quarterly and annual financials. Returns structured financial metrics."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., AAPL)",
            },
            "metrics": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "income_statement", "balance_sheet", "cash_flow",
                        "key_ratios", "quarterly_earnings", "dividends",
                        "analyst_estimates",
                    ],
                },
                "description": "Which financial data to retrieve",
                "default": ["income_statement", "key_ratios", "cash_flow"],
            },
            "period": {
                "type": "string",
                "enum": ["annual", "quarterly"],
                "description": "Reporting period",
                "default": "annual",
            },
        },
        "required": ["ticker"],
    },
    timeout=30.0,
)
@with_retry(service="yfinance")
async def financial_data_api(
    ticker: str,
    metrics: list[str] = None,
    period: str = "annual",
) -> dict[str, Any]:
    """Fetch financial data using yfinance."""
    if metrics is None:
        metrics = ["income_statement", "key_ratios", "cash_flow"]

    logger.info("financial_data_api", ticker=ticker, metrics=metrics)

    try:
        import asyncio
        loop = asyncio.get_event_loop()

        def _fetch() -> dict:
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            result: dict[str, Any] = {
                "ticker": ticker,
                "company_name": _safe(info.get("longName"), ticker),
                "source": "Yahoo Finance",
                "source_tier": 2,
            }

            if "income_statement" in metrics:
                try:
                    if period == "annual":
                        fin = stock.financials
                    else:
                        fin = stock.quarterly_financials
                    if fin is not None and not fin.empty:
                        result["income_statement"] = {
                            col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col): {
                                row: _safe(fin.at[row, col])
                                for row in fin.index
                                if _safe(fin.at[row, col]) is not None
                            }
                            for col in fin.columns[:4]  # Last 4 periods
                        }
                except Exception as e:
                    result["income_statement_error"] = str(e)

            if "balance_sheet" in metrics:
                try:
                    bs = stock.balance_sheet if period == "annual" else stock.quarterly_balance_sheet
                    if bs is not None and not bs.empty:
                        result["balance_sheet"] = {
                            col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col): {
                                row: _safe(bs.at[row, col])
                                for row in bs.index
                                if _safe(bs.at[row, col]) is not None
                            }
                            for col in bs.columns[:4]
                        }
                except Exception as e:
                    result["balance_sheet_error"] = str(e)

            if "cash_flow" in metrics:
                try:
                    cf = stock.cashflow if period == "annual" else stock.quarterly_cashflow
                    if cf is not None and not cf.empty:
                        result["cash_flow"] = {
                            col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col): {
                                row: _safe(cf.at[row, col])
                                for row in cf.index
                                if _safe(cf.at[row, col]) is not None
                            }
                            for col in cf.columns[:4]
                        }
                except Exception as e:
                    result["cash_flow_error"] = str(e)

            if "key_ratios" in metrics:
                result["key_ratios"] = {
                    "market_cap": _safe(info.get("marketCap")),
                    "enterprise_value": _safe(info.get("enterpriseValue")),
                    "pe_ratio": _safe(info.get("trailingPE")),
                    "forward_pe": _safe(info.get("forwardPE")),
                    "peg_ratio": _safe(info.get("pegRatio")),
                    "price_to_book": _safe(info.get("priceToBook")),
                    "price_to_sales": _safe(info.get("priceToSalesTrailing12Months")),
                    "ev_to_ebitda": _safe(info.get("enterpriseToEbitda")),
                    "ev_to_revenue": _safe(info.get("enterpriseToRevenue")),
                    "profit_margin": _safe(info.get("profitMargins")),
                    "operating_margin": _safe(info.get("operatingMargins")),
                    "gross_margin": _safe(info.get("grossMargins")),
                    "roe": _safe(info.get("returnOnEquity")),
                    "roa": _safe(info.get("returnOnAssets")),
                    "revenue_ttm": _safe(info.get("totalRevenue")),
                    "ebitda": _safe(info.get("ebitda")),
                    "eps": _safe(info.get("trailingEps")),
                    "beta": _safe(info.get("beta")),
                    "dividend_yield": _safe(info.get("dividendYield")),
                    "debt_to_equity": _safe(info.get("debtToEquity")),
                    "current_ratio": _safe(info.get("currentRatio")),
                    "quick_ratio": _safe(info.get("quickRatio")),
                    "revenue_growth": _safe(info.get("revenueGrowth")),
                    "earnings_growth": _safe(info.get("earningsGrowth")),
                    "free_cash_flow": _safe(info.get("freeCashflow")),
                    "52w_high": _safe(info.get("fiftyTwoWeekHigh")),
                    "52w_low": _safe(info.get("fiftyTwoWeekLow")),
                    "analyst_target_price": _safe(info.get("targetMeanPrice")),
                    "recommendation": _safe(info.get("recommendationKey")),
                }

            if "quarterly_earnings" in metrics:
                try:
                    eq = stock.earnings_dates
                    if eq is not None and not eq.empty:
                        result["quarterly_earnings"] = [
                            {
                                "date": str(idx),
                                "eps_estimate": _safe(row.get("EPS Estimate")),
                                "eps_actual": _safe(row.get("Reported EPS")),
                                "surprise_pct": _safe(row.get("Surprise(%)")),
                            }
                            for idx, row in eq.head(8).iterrows()
                        ]
                except Exception as e:
                    result["earnings_error"] = str(e)

            return result

        result = await loop.run_in_executor(None, _fetch)
        return result

    except Exception as exc:
        logger.warning("financial_data_api_fallback", ticker=ticker, error=str(exc))
        # Return empty result instead of raising — workflow continues with partial data
        return {
            "ticker": ticker,
            "source": "Yahoo Finance",
            "source_tier": 2,
            "error": str(exc),
            "key_ratios": {},
            "income_statement": {},
            "cash_flow": {},
        }
