"""
Tool: web_search
General purpose web search using DuckDuckGo.
"""
from __future__ import annotations

from typing import Any

from backend.core.errors import ToolExecutionError
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)


@registry.register(
    name="web_search",
    description=(
        "Performs a general web search and returns relevant results with titles, "
        "URLs, and snippets. Use for finding general information, recent events, "
        "industry reports, and supplementary research data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 10,
            },
            "time_range": {
                "type": "string",
                "enum": ["d", "w", "m", "y", ""],
                "description": "Time filter: d=day, w=week, m=month, y=year, empty=any",
                "default": "",
            },
        },
        "required": ["query"],
    },
    timeout=20.0,
)
@with_retry(service="web_search")
async def web_search(
    query: str,
    max_results: int = 10,
    time_range: str = "",
) -> dict[str, Any]:
    """Execute a web search using DuckDuckGo."""
    logger.info("web_search", query=query[:100])
    try:
        from duckduckgo_search import AsyncDDGS
        async with AsyncDDGS() as ddgs:
            kwargs: dict[str, Any] = {"max_results": max_results}
            if time_range:
                kwargs["timelimit"] = time_range
            results = await ddgs.atext(query, **kwargs)

        return {
            "query": query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in (results or [])
            ],
            "total": len(results or []),
            "source": "DuckDuckGo",
            "source_tier": 5,
        }
    except Exception as exc:
        raise ToolExecutionError(f"Web search failed: {exc}", code="WEB_SEARCH_ERROR")
