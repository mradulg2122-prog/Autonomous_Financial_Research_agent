"""
ARA-1 Memory API Routes
GET /memory/short-term/{session_id} - Get Redis session state
GET /memory/episodic - Get episodic memory records
GET /memory/long-term/search - Semantic search in Qdrant
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_session
from backend.memory.episodic import EpisodicMemoryStore
from backend.memory.long_term import LongTermMemory
from backend.memory.short_term import ShortTermMemory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/short-term/{session_id}")
async def get_short_term_memory(session_id: str) -> dict:
    """Get the full short-term memory state for a session."""
    stm = ShortTermMemory(session_id)
    state = await stm.get_full_state()
    tool_outputs = await stm.get_tool_outputs()
    findings = await stm.get_agent_findings()
    return {
        "session_id": session_id,
        "state": state,
        "tool_outputs": tool_outputs[:20],  # Last 20
        "agent_findings": findings,
        "total_tool_outputs": len(tool_outputs),
    }


@router.get("/episodic")
async def get_episodic_memories(
    limit: int = 20,
    ticker: str = Query(default=""),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Get episodic memory records."""
    store = EpisodicMemoryStore()
    memories = await store.get_recent_episodes(limit=limit, ticker=ticker or None)
    return {
        "memories": [
            {
                "episode_id": str(m.id),
                "session_id": str(m.session_id),
                "query": m.query,
                "company_ticker": m.company_ticker,
                "tools_used": m.tools_used,
                "agents_executed": m.agents_executed,
                "evaluation_score": m.evaluation_score,
                "success": m.success,
                "created_at": m.created_at.isoformat(),
            }
            for m in memories
        ],
        "total": len(memories),
    }


@router.get("/long-term/search")
async def search_long_term_memory(
    query: str = Query(..., min_length=3),
    top_k: int = Query(default=10, ge=1, le=50),
    filter_type: str = Query(default=""),
) -> dict:
    """Semantic search in the Qdrant vector database."""
    ltm = LongTermMemory()
    results = await ltm.search(
        query=query,
        top_k=top_k,
        filter_metadata={"type": filter_type} if filter_type else None,
    )
    return {
        "query": query,
        "results": results,
        "total": len(results),
    }


@router.get("/long-term/stats")
async def get_vector_db_stats() -> dict:
    """Get Qdrant collection statistics."""
    ltm = LongTermMemory()
    count = await ltm.count()
    return {
        "collection": ltm.collection,
        "total_documents": count,
    }
