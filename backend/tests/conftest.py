"""
pytest configuration and shared fixtures.
"""
import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session-scoped async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
