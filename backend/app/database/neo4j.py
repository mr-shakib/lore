"""
Neo4j graph database connection — STUB (deferred to M6).

The Company Context Graph queries run against PostgreSQL for MVP.
This module exists to avoid import errors in any code that references it.
All functions are safe no-ops. Re-enable Neo4j by restoring this module
once workspace count justifies the graph traversal overhead.
"""

import structlog

logger = structlog.get_logger(__name__)


# ── Startup / shutdown (no-ops) ───────────────────────────────────────────────

async def init_graph_db() -> None:
    """No-op stub — Neo4j deferred to M6. PostgreSQL handles all graph queries."""
    logger.info("neo4j_stub_skipped", reason="using_postgres_for_graph_queries")


async def close_graph_db() -> None:
    """No-op stub."""
    pass


def get_driver():
    raise RuntimeError(
        "Neo4j is not enabled. Graph queries run via PostgreSQL for MVP. "
        "See app/services/context_graph.py."
    )


async def get_session():
    """Stub — kept for import compatibility. Not used by any route."""
    raise RuntimeError(
        "Neo4j get_session() is not available. Use get_connection() from app.database.postgres."
    )
    yield  # make it a generator so existing Depends() calls fail loudly rather than silently

    logger.info("neo4j_schema_ensured")
