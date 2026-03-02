"""
Test suite for Lore backend.

Uses pytest-asyncio with httpx.AsyncClient (no live database required for unit tests).
Integration tests (marked with @pytest.mark.integration) require a running database.

Run unit tests only:
    pytest -m "not integration"

Run all tests (requires running Docker services):
    pytest
"""
