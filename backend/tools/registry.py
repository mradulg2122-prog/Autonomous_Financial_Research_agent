"""
ARA-1 Tool Registry
Registers all tools with their OpenAI function-calling schemas.
Provides a unified interface for agents to discover and invoke tools.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from backend.core.errors import ToolError, ToolExecutionError, ToolNotFoundError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ToolDefinition:
    """Wraps a tool with its OpenAI function-calling schema."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
        timeout: float = 30.0,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.timeout = timeout

    def to_openai_schema(self) -> dict:
        """Return OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Central registry for all ARA-1 tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        timeout: float = 30.0,
    ) -> Callable:
        """Decorator to register a tool."""
        def decorator(func: Callable) -> Callable:
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                func=func,
                timeout=timeout,
            )
            logger.debug("tool_registered", name=name)
            return func
        return decorator

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not found in registry.", code="TOOL_NOT_FOUND")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_openai_schemas(self, tool_names: Optional[list[str]] = None) -> list[dict]:
        """Return OpenAI function-calling schemas for specified (or all) tools."""
        names = tool_names or list(self._tools.keys())
        return [self._tools[n].to_openai_schema() for n in names if n in self._tools]

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a tool by name with timing and error handling."""
        tool = self.get(tool_name)
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                tool.func(**arguments),
                timeout=tool.timeout,
            )
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "tool_executed",
                tool=tool_name,
                duration_ms=round(duration_ms, 2),
                session_id=session_id,
            )
            return {"success": True, "result": result, "tool": tool_name, "duration_ms": duration_ms}
        except asyncio.TimeoutError:
            raise ToolExecutionError(
                f"Tool '{tool_name}' timed out after {tool.timeout}s",
                code="TOOL_TIMEOUT",
            )
        except ToolError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool '{tool_name}' failed: {exc}", code="TOOL_EXEC_ERROR"
            )


# Singleton registry instance
registry = ToolRegistry()
