"""
ARA-1 Integration Tests — API Endpoints
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
async def client():
    """Create test client with mocked dependencies."""
    with patch("backend.db.database.init_db"), \
         patch("backend.db.database.close_db"), \
         patch("backend.memory.short_term.get_redis", return_value=AsyncMock()), \
         patch("backend.memory.long_term.ensure_collection", return_value=None):
        from backend.api.main import app
        from backend.db.database import get_session

        async def override_get_session():
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=None)
            mock_scalars = MagicMock()
            mock_scalars.all = MagicMock(return_value=[])
            mock_result.scalars = MagicMock(return_value=mock_scalars)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.get = AsyncMock(return_value=None)
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint returns 200."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ARA-1"


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test root endpoint returns API info."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "service" in data
    assert "docs" in data


@pytest.mark.asyncio
async def test_list_agents(client):
    """Test agents registry endpoint."""
    resp = await client.get("/api/v1/agents/registry")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["agents"]) == 9
    agent_names = [a["name"] for a in data["agents"]]
    assert "planner_agent" in agent_names
    assert "evaluation_agent" in agent_names


@pytest.mark.asyncio
async def test_list_tools(client):
    """Test tools endpoint returns all registered tools."""
    resp = await client.get("/api/v1/agents/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 15


@pytest.mark.asyncio
async def test_list_sessions_empty(client):
    """Test sessions list returns empty state."""
    resp = await client.get("/api/v1/research")
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert len(data["sessions"]) == 0


@pytest.mark.asyncio
async def test_docs_available(client):
    """Test OpenAPI docs are accessible."""
    resp = await client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_report_not_found(client):
    """Test 404 response for non-existent report."""
    resp = await client.get("/api/v1/reports/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 404
