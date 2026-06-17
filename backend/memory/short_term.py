"""
ARA-1 Short-Term Memory — Redis
Stores conversation context, in-flight state, and intermediate results.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import redis.asyncio as aioredis

from backend.core.config import settings
from backend.core.errors import CacheError
from backend.core.logging import get_logger

logger = get_logger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Get or create the Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_connection_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


class ShortTermMemory:
    """
    Redis-backed short-term memory for a research session.
    Stores: research state, tool outputs, intermediate findings.
    """

    def __init__(self, session_id: str, ttl: int = None):
        self.session_id = session_id
        self.ttl = ttl or settings.redis_ttl_seconds
        self._prefix = f"ara1:session:{session_id}"

    def _key(self, field: str) -> str:
        return f"{self._prefix}:{field}"

    async def set(self, field: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in short-term memory. Fails silently if Redis is unavailable."""
        try:
            r = await get_redis()
            serialized = json.dumps(value, default=str)
            await r.setex(self._key(field), ttl or self.ttl, serialized)
        except Exception as exc:
            logger.warning("cache_set_error", field=field, error=str(exc))

    async def get(self, field: str) -> Optional[Any]:
        """Retrieve a value from short-term memory."""
        try:
            r = await get_redis()
            raw = await r.get(self._key(field))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("cache_get_error", field=field, error=str(exc))
            return None

    async def delete(self, field: str) -> None:
        """Remove a field from memory."""
        r = await get_redis()
        await r.delete(self._key(field))

    async def append_to_list(self, field: str, item: Any) -> None:
        """Append an item to a list-type field. Fails silently if Redis is unavailable."""
        try:
            r = await get_redis()
            serialized = json.dumps(item, default=str)
            await r.rpush(self._key(field), serialized)
            await r.expire(self._key(field), self.ttl)
        except Exception as exc:
            logger.warning("cache_append_error", field=field, error=str(exc))

    async def get_list(self, field: str) -> list[Any]:
        """Get all items from a list-type field."""
        try:
            r = await get_redis()
            items = await r.lrange(self._key(field), 0, -1)
            return [json.loads(i) for i in items]
        except Exception:
            return []

    async def update_state(self, state_update: dict[str, Any]) -> None:
        """Batch update multiple state fields."""
        for field, value in state_update.items():
            await self.set(field, value)

    async def get_full_state(self) -> dict[str, Any]:
        """Retrieve all fields for this session."""
        try:
            r = await get_redis()
            pattern = f"{self._prefix}:*"
            keys = await r.keys(pattern)
            state: dict[str, Any] = {}
            for key in keys:
                field = key.replace(f"{self._prefix}:", "", 1)
                raw = await r.get(key)
                if raw:
                    try:
                        state[field] = json.loads(raw)
                    except json.JSONDecodeError:
                        state[field] = raw
            return state
        except Exception as exc:
            logger.warning("state_retrieval_error", error=str(exc))
            return {}

    async def clear(self) -> None:
        """Clear all memory for this session."""
        try:
            r = await get_redis()
            pattern = f"{self._prefix}:*"
            keys = await r.keys(pattern)
            if keys:
                await r.delete(*keys)
        except Exception as exc:
            logger.warning("cache_clear_error", error=str(exc))

    async def store_tool_output(self, tool_name: str, output: Any) -> None:
        """Store a tool's output in the tool results list."""
        await self.append_to_list("tool_outputs", {
            "tool": tool_name,
            "output": output,
        })

    async def get_tool_outputs(self) -> list[dict]:
        """Get all tool outputs for this session."""
        return await self.get_list("tool_outputs")

    async def store_agent_finding(self, agent: str, finding: Any) -> None:
        """Store a finding from an agent."""
        await self.append_to_list("agent_findings", {
            "agent": agent,
            "finding": finding,
        })

    async def get_agent_findings(self) -> list[dict]:
        """Get all agent findings."""
        return await self.get_list("agent_findings")

    async def increment_counter(self, counter: str) -> int:
        """Increment a numeric counter, return new value."""
        try:
            r = await get_redis()
            val = await r.incr(self._key(counter))
            await r.expire(self._key(counter), self.ttl)
            return val
        except Exception:
            return 0
