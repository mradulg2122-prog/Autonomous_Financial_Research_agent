"""
Tool: market_data_tool
Retrieves real-time and historical market data: price, volume, technicals.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)


@registry.register(
    name="market_data_tool",
    description=(
        "Retrieves market data: current price, historical prices, volume, "
        "52-week range, moving averages, RSI, and other technical indicators. "
        "Use for price performance, trend analysis, and technical context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol",
            },
            "period": {
                "type": "string",
                "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"],
                "description": "Historical data period",
                "default": "1y",
            },
            "interval": {
                "type": "string",
                "enum": ["1d", "1wk", "1mo"],
                "description": "Data interval",
                "default": "1d",
            },
            "include_technicals": {
                "type": "boolean",
                "description": "Calculate technical indicators (MA20, MA50, MA200, RSI)",
                "default": True,
            },
        },
        "required": ["ticker"],
    },
    timeout=25.0,
)
@with_retry(service="yfinance")
async def market_data_tool(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    include_technicals: bool = True,
) -> dict[str, Any]:
    """Fetch market data and compute technical indicators."""
    logger.info("market_data_tool", ticker=ticker, period=period)

    loop = asyncio.get_event_loop()

    def _fetch():
        import pandas as pd
        import numpy as np

        stock = yf.Ticker(ticker)
        info = stock.info or {}

        # Historical prices
        hist = stock.history(period=period, interval=interval)
        price_data: list[dict] = []

        if hist is not None and not hist.empty:
            # Recent price snapshot
            latest = hist.iloc[-1]
            first = hist.iloc[0]
            price_return = ((latest["Close"] - first["Close"]) / first["Close"] * 100)

            # Technical indicators
            technicals: dict[str, Any] = {}
            if include_technicals and len(hist) >= 20:
                closes = hist["Close"]
                technicals["ma_20"] = round(float(closes.rolling(20).mean().iloc[-1]), 2)
                if len(hist) >= 50:
                    technicals["ma_50"] = round(float(closes.rolling(50).mean().iloc[-1]), 2)
                if len(hist) >= 200:
                    technicals["ma_200"] = round(float(closes.rolling(200).mean().iloc[-1]), 2)

                # RSI (14-period)
                delta = closes.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                technicals["rsi_14"] = round(float(rsi.iloc[-1]), 2)

                # Volume analysis
                if "Volume" in hist.columns:
                    avg_vol_20 = hist["Volume"].rolling(20).mean().iloc[-1]
                    technicals["avg_volume_20d"] = int(avg_vol_20) if not pd.isna(avg_vol_20) else None

            # Price history (last 30 data points for chart)
            recent = hist.tail(30)
            price_data = [
                {
                    "date": str(idx.date()),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row.get("Volume", 0)),
                }
                for idx, row in recent.iterrows()
            ]

            return {
                "ticker": ticker,
                "company_name": info.get("longName", ticker),
                "current_price": round(float(latest["Close"]), 2),
                "period_return_pct": round(price_return, 2),
                "period": period,
                "high": round(float(hist["High"].max()), 2),
                "low": round(float(hist["Low"].min()), 2),
                "avg_volume": int(hist["Volume"].mean()) if "Volume" in hist.columns else None,
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "50d_ma": info.get("fiftyDayAverage"),
                "200d_ma": info.get("twoHundredDayAverage"),
                "technicals": technicals,
                "price_history": price_data,
                "data_points": len(hist),
                "source": "Yahoo Finance Market Data",
                "source_tier": 2,
            }
        else:
            return {
                "ticker": ticker,
                "error": "No historical data available",
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
            }

    return await loop.run_in_executor(None, _fetch)
