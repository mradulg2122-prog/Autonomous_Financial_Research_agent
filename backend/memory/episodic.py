"""
ARA-1 Episodic Memory — PostgreSQL
Stores complete research episodes: query → reasoning → findings → report.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db_session
from backend.db.models import EpisodicMemory, ResearchSession
from backend.core.errors import EpisodicMemoryError
from backend.core.logging import get_logger
from backend.memory.long_term import LongTermMemory

logger = get_logger(__name__)


class EpisodicMemoryStore:
    """
    PostgreSQL-backed episodic memory.
    Stores full research trajectory for retrospective analysis and learning.
    Also mirrors key summary to Qdrant for semantic search across past episodes.
    """

    def __init__(self) -> None:
        self._ltm = LongTermMemory()

    async def store_episode(
        self,
        session_id: str,
        query: str,
        company_ticker: Optional[str],
        reasoning_path: list[dict],
        tools_used: list[str],
        agents_executed: list[str],
        errors_encountered: list[dict],
        conflicts_resolved: list[dict],
        final_report_id: Optional[str],
        evaluation_score: Optional[float],
        success: bool,
    ) -> str:
        """
        Persist an episodic memory record.
        Returns the episode ID.
        """
        try:
            async with get_db_session() as db:
                episode = EpisodicMemory(
                    session_id=uuid.UUID(session_id),
                    query=query,
                    company_ticker=company_ticker,
                    reasoning_path=reasoning_path,
                    tools_used=tools_used,
                    agents_executed=agents_executed,
                    errors_encountered=errors_encountered,
                    conflicts_resolved=conflicts_resolved,
                    final_report_id=uuid.UUID(final_report_id) if final_report_id else None,
                    evaluation_score=evaluation_score,
                    success=success,
                )
                db.add(episode)
                await db.flush()
                episode_id = str(episode.id)

        except Exception as exc:
            # Log and continue — do NOT crash the research workflow over episodic storage
            logger.warning("episodic_db_store_failed", error=str(exc), session_id=session_id)
            return "episodic-store-failed"

        try:
            # Also store a compressed summary in Qdrant for semantic retrieval
            summary = self._build_summary(
                query=query,
                ticker=company_ticker,
                agents=agents_executed,
                tools=tools_used,
                score=evaluation_score,
            )
            qdrant_id = await self._ltm.store(
                text=summary,
                metadata={
                    "type": "episodic_memory",
                    "session_id": session_id,
                    "episode_id": episode_id,
                    "company_ticker": company_ticker or "",
                    "success": success,
                    "score": evaluation_score or 0.0,
                },
                doc_id=episode_id,
            )

            # Update Qdrant ID reference
            async with get_db_session() as db:
                ep = await db.get(EpisodicMemory, uuid.UUID(episode_id))
                if ep:
                    ep.qdrant_id = qdrant_id
                    await db.flush()

        except Exception as exc:
            logger.warning("episodic_qdrant_store_failed", error=str(exc), episode_id=episode_id)

        logger.info("episodic_memory_stored", episode_id=episode_id, ticker=company_ticker)
        return episode_id

    def _build_summary(
        self,
        query: str,
        ticker: Optional[str],
        agents: list[str],
        tools: list[str],
        score: Optional[float],
    ) -> str:
        return (
            f"Research Query: {query}\n"
            f"Company: {ticker or 'N/A'}\n"
            f"Agents Used: {', '.join(agents)}\n"
            f"Tools Used: {', '.join(tools)}\n"
            f"Evaluation Score: {score:.2f if score else 'N/A'}"
        )

    async def search_similar_episodes(
        self, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Find semantically similar past research episodes."""
        return await self._ltm.search(
            query=query,
            top_k=top_k,
            filter_metadata={"type": "episodic_memory"},
        )

    async def get_episode_by_session(
        self, session_id: str
    ) -> Optional[EpisodicMemory]:
        """Retrieve episode record by session ID."""
        try:
            async with get_db_session() as db:
                result = await db.execute(
                    select(EpisodicMemory).where(
                        EpisodicMemory.session_id == uuid.UUID(session_id)
                    )
                )
                return result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("episode_retrieval_error", error=str(exc))
            return None

    async def get_recent_episodes(
        self, limit: int = 20, ticker: Optional[str] = None
    ) -> list[EpisodicMemory]:
        """Get most recent episodic memory records."""
        try:
            async with get_db_session() as db:
                query_stmt = select(EpisodicMemory).order_by(
                    EpisodicMemory.created_at.desc()
                )
                if ticker:
                    query_stmt = query_stmt.where(
                        EpisodicMemory.company_ticker == ticker
                    )
                query_stmt = query_stmt.limit(limit)
                result = await db.execute(query_stmt)
                return list(result.scalars().all())
        except Exception:
            return []
