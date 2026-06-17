"""
ARA-1 Custom Exceptions and Error Hierarchy
"""
from __future__ import annotations

from typing import Any, Optional


class ARA1Error(Exception):
    """Base exception for all ARA-1 errors."""

    def __init__(self, message: str, code: str = "ARA1_ERROR", details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details

    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# ── Agent Errors ──────────────────────────────────────────────
class AgentError(ARA1Error):
    """Error raised by an agent during execution."""


class PlannerError(AgentError):
    """Error raised by the Planner Agent."""


class AgentTimeoutError(AgentError):
    """Agent exceeded timeout."""


class MaxIterationsError(AgentError):
    """Agent exceeded maximum iteration count."""


# ── Tool Errors ───────────────────────────────────────────────
class ToolError(ARA1Error):
    """Error raised by a tool."""


class ToolNotFoundError(ToolError):
    """Requested tool does not exist in registry."""


class ToolExecutionError(ToolError):
    """Tool failed during execution."""


class ToolTimeoutError(ToolError):
    """Tool call timed out."""


# ── API / External Service Errors ─────────────────────────────
class ExternalServiceError(ARA1Error):
    """Error communicating with an external service."""

    def __init__(
        self,
        message: str,
        service: str,
        status_code: Optional[int] = None,
        **kwargs: Any,
    ):
        super().__init__(message, **kwargs)
        self.service = service
        self.status_code = status_code


class RateLimitError(ExternalServiceError):
    """API rate limit exceeded."""


class CircuitOpenError(ExternalServiceError):
    """Circuit breaker is open — service unavailable."""


class APIAuthError(ExternalServiceError):
    """Authentication failure with external API."""


# ── Memory Errors ─────────────────────────────────────────────
class MemoryError(ARA1Error):
    """Error in the memory subsystem."""


class VectorDBError(MemoryError):
    """Qdrant operation failed."""


class CacheError(MemoryError):
    """Redis operation failed."""


class EpisodicMemoryError(MemoryError):
    """PostgreSQL episodic memory operation failed."""


# ── RAG Errors ────────────────────────────────────────────────
class RAGError(ARA1Error):
    """Error in the RAG pipeline."""


class EmbeddingError(RAGError):
    """Failed to generate embeddings."""


class RetrievalError(RAGError):
    """Document retrieval failed."""


# ── Validation Errors ─────────────────────────────────────────
class ValidationError(ARA1Error):
    """Input validation failure."""


class ReportGenerationError(ARA1Error):
    """Report generation failed."""
