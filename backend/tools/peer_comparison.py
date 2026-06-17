"""
Tool: peer_comparison
Compares a company against its industry peers on key financial metrics.
"""
from __future__ import annotations

import asyncio
from typing import Any

import yfinance as yf

from backend.core.errors import ToolExecutionError
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)


def _get_peer_metrics(ticker: str) -> dict[str, Any]:
    """Fetch key metrics for a single ticker."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        return {
            "ticker": ticker,
            "name": info.get("longName", ticker),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            "price_to_book": info.get("priceToBook"),
            "profit_margin": info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "revenue_ttm": info.get("totalRevenue"),
            "gross_margin": info.get("grossMargins"),
            "beta": info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc)}


@registry.register(
    name="peer_comparison",
    description=(
        "Compares a company against industry peers on financial metrics. "
        "Returns a side-by-side comparison of valuation, profitability, growth, "
        "and financial health metrics. Use this to assess competitive positioning."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Primary company ticker symbol",
            },
            "peers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of peer ticker symbols to compare against. If empty, auto-detected from sector.",
                "default": [],
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Metrics to compare",
                "default": ["pe_ratio", "ev_to_ebitda", "profit_margin", "revenue_growth", "roe"],
            },
        },
        "required": ["ticker"],
    },
    timeout=45.0,
)
@with_retry(service="peer_comparison")
async def peer_comparison(
    ticker: str,
    peers: list[str] = None,
    metrics: list[str] = None,
) -> dict[str, Any]:
    """Compare company against peers."""
    if metrics is None:
        metrics = ["pe_ratio", "ev_to_ebitda", "profit_margin", "revenue_growth", "roe"]
    if peers is None:
        peers = []

    logger.info("peer_comparison", ticker=ticker, peers=peers)

    # Auto-detect peers if not provided
    if not peers:
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info or {})
            sector = info.get("sector", "")
            industry = info.get("industry", "")

            # Common peer mappings
            SECTOR_PEERS: dict[str, list[str]] = {
                "Technology": ["AAPL", "MSFT", "GOOGL", "META", "AMZN"],
                "Healthcare": ["JNJ", "PFE", "UNH", "ABBV", "MRK"],
                "Financials": ["JPM", "BAC", "WFC", "GS", "MS"],
                "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
                "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
                "Industrials": ["HON", "MMM", "GE", "CAT", "BA"],
            }
            peers = [p for p in SECTOR_PEERS.get(sector, ["SPY", "QQQ", "DIA"]) if p != ticker][:4]
        except Exception:
            peers = []

    all_tickers = [ticker] + peers

    # Fetch metrics concurrently
    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, _get_peer_metrics, t) for t in all_tickers],
        return_exceptions=True,
    )

    companies = []
    for r in results:
        if isinstance(r, Exception):
            continue
        companies.append(r)

    # Calculate rankings for each metric
    rankings: dict[str, list[dict]] = {}
    for metric in metrics:
        values = [
            {"ticker": c["ticker"], "value": c.get(metric)}
            for c in companies
            if c.get(metric) is not None
        ]
        values.sort(key=lambda x: x["value"] or 0, reverse=True)
        rankings[metric] = values

    # Find primary company rank
    primary_data = next((c for c in companies if c["ticker"] == ticker), {})
    peer_data = [c for c in companies if c["ticker"] != ticker]

    return {
        "ticker": ticker,
        "primary_company": primary_data,
        "peers": peer_data,
        "rankings": rankings,
        "peer_tickers_used": peers,
        "metrics_compared": metrics,
        "source": "Yahoo Finance Peer Comparison",
        "source_tier": 2,
    }
