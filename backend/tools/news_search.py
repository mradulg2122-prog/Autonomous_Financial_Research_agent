"""
Tool: news_search
Financial news search with sentiment pre-tagging.
"""
from __future__ import annotations

from typing import Any

import httpx

from backend.core.config import settings
from backend.core.errors import ToolExecutionError
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)


@registry.register(
    name="news_search",
    description=(
        "Search for recent financial news about a company or topic. "
        "Returns articles with titles, descriptions, URLs, dates, and sources. "
        "Use for news sentiment, recent developments, and market reactions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (company name, ticker, topic)",
            },
            "from_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format",
                "default": "",
            },
            "to_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format",
                "default": "",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of articles",
                "default": 15,
            },
            "sort_by": {
                "type": "string",
                "enum": ["publishedAt", "relevancy", "popularity"],
                "default": "publishedAt",
            },
        },
        "required": ["query"],
    },
    timeout=20.0,
)
@with_retry(service="news_search")
async def news_search(
    query: str,
    from_date: str = "",
    to_date: str = "",
    max_results: int = 15,
    sort_by: str = "publishedAt",
) -> dict[str, Any]:
    """Search for news using NewsAPI or DuckDuckGo fallback."""
    logger.info("news_search", query=query[:100])

    articles = []

    # Try NewsAPI if key is available
    if settings.news_api_key:
        try:
            params: dict[str, Any] = {
                "q": query,
                "apiKey": settings.news_api_key,
                "pageSize": min(max_results, 100),
                "sortBy": sort_by,
                "language": "en",
            }
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://newsapi.org/v2/everything", params=params
                )
                if resp.status_code == 200:
                    data = resp.json()
                    articles = [
                        {
                            "title": a.get("title", ""),
                            "description": a.get("description", ""),
                            "url": a.get("url", ""),
                            "source": a.get("source", {}).get("name", ""),
                            "published_at": a.get("publishedAt", ""),
                            "content": (a.get("content") or "")[:500],
                        }
                        for a in data.get("articles", [])
                    ]
        except Exception as exc:
            logger.warning("newsapi_error", error=str(exc))

    # Fallback: DuckDuckGo news (sync API via executor)
    if not articles:
        try:
            import asyncio
            from duckduckgo_search import DDGS

            def _ddg_news() -> list:
                with DDGS() as ddgs:
                    return list(ddgs.news(query, max_results=max_results))

            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(None, _ddg_news)
            articles = [
                {
                    "title": r.get("title", ""),
                    "description": r.get("body", ""),
                    "url": r.get("url", ""),
                    "source": r.get("source", ""),
                    "published_at": r.get("date", ""),
                    "content": "",
                }
                for r in (raw or [])
            ]
        except Exception as exc:
            logger.warning("ddg_news_error", error=str(exc))
            # Return empty gracefully — don't crash the pipeline

    return {
        "query": query,
        "articles": articles[:max_results],
        "total": len(articles),
        "source": "NewsAPI + DuckDuckGo News",
        "source_tier": 4,
    }
