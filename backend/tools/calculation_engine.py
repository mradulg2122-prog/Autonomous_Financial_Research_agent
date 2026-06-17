"""
Tool: calculation_engine
Performs financial ratio and metric calculations from raw financial data.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from backend.core.logging import get_logger
from backend.tools.registry import registry

logger = get_logger(__name__)


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    try:
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


def _pct_change(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    if current is None or prior is None or prior == 0:
        return None
    return ((current - prior) / abs(prior)) * 100


KEY_ALIASES: dict[str, list[str]] = {
    "totalRevenue": ["totalRevenue", "revenue_ttm", "revenue"],
    "revenue_ttm": ["revenue_ttm", "totalRevenue", "revenue"],
    "netIncome": ["netIncome", "net_income"],
    "grossProfit": ["grossProfit", "gross_profit"],
    "ebit": ["ebit", "operatingIncome", "operating_income"],
    "ebitda": ["ebitda"],
    "roe": ["roe", "returnOnEquity"],
    "roa": ["roa", "returnOnAssets"],
    "current_ratio": ["current_ratio", "currentRatio"],
    "quick_ratio": ["quick_ratio", "quickRatio"],
    "cash": ["cash", "cashAndCashEquivalents", "cash_equivalents"],
    "totalCurrentLiabilities": ["totalCurrentLiabilities", "currentLiabilities", "total_current_liabilities"],
    "debt_to_equity": ["debt_to_equity", "debtToEquity"],
    "totalDebt": ["totalDebt", "total_debt"],
    "totalAssets": ["totalAssets", "total_assets"],
    "interestExpense": ["interestExpense", "interest_expense"],
    "pe_ratio": ["pe_ratio", "trailingPE", "pe"],
    "forward_pe": ["forward_pe", "forwardPE"],
    "peg_ratio": ["peg_ratio", "pegRatio"],
    "price_to_book": ["price_to_book", "priceToBook"],
    "price_to_sales": ["price_to_sales", "priceToSalesTrailing12Months"],
    "ev_to_ebitda": ["ev_to_ebitda", "enterpriseToEbitda"],
    "ev_to_revenue": ["ev_to_revenue", "enterpriseToRevenue"],
    "revenue_growth": ["revenue_growth", "revenueGrowth", "revenue_growth_yoy"],
    "earnings_growth": ["earnings_growth", "earningsGrowth", "earnings_growth_yoy"],
    "eps_growth": ["eps_growth", "epsGrowth"],
    "costOfRevenue": ["costOfRevenue", "cost_of_revenue"],
    "inventory": ["inventory"],
    "netReceivables": ["netReceivables", "net_receivables"],
    "totalStockholderEquity": ["totalStockholderEquity", "total_equity", "stockholderEquity"],
}


@registry.register(
    name="calculation_engine",
    description=(
        "Calculates financial ratios and metrics from raw financial data. "
        "Computes: profitability ratios, liquidity ratios, leverage ratios, "
        "valuation multiples, growth rates, DuPont analysis, and DCF inputs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "financial_data": {
                "type": "object",
                "description": "Raw financial data (revenue, earnings, assets, liabilities, etc.)",
            },
            "calculations": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "profitability", "liquidity", "leverage",
                        "valuation", "growth", "dupont", "efficiency",
                    ],
                },
                "description": "Which calculations to perform",
                "default": ["profitability", "liquidity", "leverage", "valuation"],
            },
        },
        "required": ["financial_data"],
    },
    timeout=10.0,
)
async def calculation_engine(
    financial_data: dict[str, Any],
    calculations: list[str] = None,
) -> dict[str, Any]:
    """Calculate financial ratios from provided data."""
    if calculations is None:
        calculations = ["profitability", "liquidity", "leverage", "valuation"]

    logger.info("calculation_engine", calculations=calculations)

    fd = financial_data
    results: dict[str, Any] = {}

    # Helper to get values
    def g(key: str, default: Optional[float] = None) -> Optional[float]:
        candidates = KEY_ALIASES.get(key, [key])
        val = None
        for k in candidates:
            if k in fd:
                val = fd[k]
                break
            elif "key_ratios" in fd and k in fd["key_ratios"]:
                val = fd["key_ratios"][k]
                break
        if val is None:
            val = default
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    if "profitability" in calculations:
        revenue = g("totalRevenue") or g("revenue_ttm")
        net_income = g("netIncome")
        gross_profit = g("grossProfit")
        ebit = g("ebit")
        ebitda = g("ebitda")

        results["profitability"] = {
            "gross_margin": _safe_div(gross_profit, revenue),
            "operating_margin": g("operating_margin") or _safe_div(ebit, revenue),
            "net_profit_margin": g("profit_margin") or _safe_div(net_income, revenue),
            "ebitda_margin": _safe_div(ebitda, revenue),
            "roe": g("roe"),
            "roa": g("roa"),
        }

    if "liquidity" in calculations:
        results["liquidity"] = {
            "current_ratio": g("current_ratio"),
            "quick_ratio": g("quick_ratio"),
            "cash_ratio": _safe_div(g("cash"), g("totalCurrentLiabilities")),
        }

    if "leverage" in calculations:
        results["leverage"] = {
            "debt_to_equity": g("debt_to_equity"),
            "debt_to_assets": _safe_div(g("totalDebt"), g("totalAssets")),
            "interest_coverage": _safe_div(g("ebit"), g("interestExpense")),
            "net_debt": (g("totalDebt") or 0) - (g("cash") or 0),
        }

    if "valuation" in calculations:
        results["valuation"] = {
            "pe_ratio": g("pe_ratio"),
            "forward_pe": g("forward_pe"),
            "peg_ratio": g("peg_ratio"),
            "price_to_book": g("price_to_book"),
            "price_to_sales": g("price_to_sales"),
            "ev_to_ebitda": g("ev_to_ebitda"),
            "ev_to_revenue": g("ev_to_revenue"),
        }

    if "growth" in calculations:
        results["growth"] = {
            "revenue_growth_yoy": g("revenue_growth"),
            "earnings_growth_yoy": g("earnings_growth"),
            "eps_growth": g("eps_growth"),
        }

    if "efficiency" in calculations:
        revenue = g("totalRevenue") or g("revenue_ttm")
        results["efficiency"] = {
            "asset_turnover": _safe_div(revenue, g("totalAssets")),
            "inventory_turnover": _safe_div(g("costOfRevenue"), g("inventory")),
            "receivables_turnover": _safe_div(revenue, g("netReceivables")),
        }

    if "dupont" in calculations:
        net_margin = g("profit_margin")
        asset_turnover = _safe_div(
            g("totalRevenue") or g("revenue_ttm"), g("totalAssets")
        )
        equity_multiplier = _safe_div(g("totalAssets"), g("totalStockholderEquity"))
        roe_dupont = None
        if all(v is not None for v in [net_margin, asset_turnover, equity_multiplier]):
            roe_dupont = net_margin * asset_turnover * equity_multiplier

        results["dupont"] = {
            "net_profit_margin": net_margin,
            "asset_turnover": asset_turnover,
            "equity_multiplier": equity_multiplier,
            "roe_dupont": roe_dupont,
        }

    # Remove None-only dicts
    results = {
        k: {mk: mv for mk, mv in v.items() if mv is not None}
        for k, v in results.items()
        if isinstance(v, dict)
    }

    return {
        "calculations": results,
        "input_keys_used": list(financial_data.keys()),
        "source": "ARA-1 Calculation Engine",
    }
