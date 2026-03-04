"""
PostgreSQL connection via SQLAlchemy (async) + asyncpg.

Used for:
  - Storing raw CaptureEvents (structured event log)
  - Rule metadata (complement to Neo4j graph representation)
  - Workspace / team management data

Tables are defined in migrations/001_initial.sql.
At runtime, SQLAlchemy is used in "core" (not ORM) mode to keep things fast
and explicit — no magic lazy loading on async paths.
"""

from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings

logger = structlog.get_logger(__name__)

# Module-level engine singleton (created on startup, closed on shutdown)
_engine: AsyncEngine | None = None


async def init_db() -> None:
    """Create the async engine and verify the database is reachable."""
    global _engine

    # asyncpg's SQLAlchemy dialect strips the project-ref suffix from usernames
    # that contain a dot (e.g. postgres.bamqnbchfjwcbggxporr → postgres).
    # Passing the full username via connect_args bypasses this bug.
    from sqlalchemy.engine import make_url
    import ssl as _ssl

    parsed = make_url(settings.database_url)
    ssl_ctx = _ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = _ssl.CERT_NONE

    connect_args: dict = {
        "ssl": ssl_ctx,
        # Supabase uses PgBouncer in transaction mode which does not support
        # prepared statements — disabling the cache avoids DuplicatePreparedStatementError
        "statement_cache_size": 0,
        # Fail fast if the host is unreachable (e.g. wrong env var on Render)
        "timeout": 10,
    }
    if parsed.username and "." in parsed.username:
        connect_args["user"] = parsed.username

    # Use NullPool in testing so connections don't leak between test cases
    pool_class = NullPool if settings.environment == "testing" else None

    kwargs: dict = dict(
        echo=settings.debug,
        connect_args=connect_args,
    )
    if pool_class:
        kwargs["poolclass"] = pool_class

    _engine = create_async_engine(settings.database_url, **kwargs)

    # Smoke test — will raise immediately if credentials are wrong
    async with _engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))

    logger.info("postgres_connected", url=_redact(settings.database_url))


async def close_db() -> None:
    """Dispose the engine (returns all connections to pool, then closes)."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("postgres_disconnected")


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("PostgreSQL engine not initialized. Call init_db() first.")
    return _engine


async def get_connection() -> AsyncGenerator[AsyncConnection, None]:
    """
    FastAPI dependency — yields an open database connection inside a transaction.

    Uses ``engine.begin()`` so the transaction is committed automatically when
    the request handler returns successfully, and rolled back on any exception.
    Handlers that need to commit earlier (e.g. to release locks) can call
    ``await conn.commit()`` explicitly — SQLAlchemy will start a new implicit
    transaction for subsequent statements.

    Usage::

        @router.get("/example")
        async def example(conn: AsyncConnection = Depends(get_connection)):
            result = await conn.execute(text("SELECT 1"))
    """
    async with get_engine().begin() as conn:
        yield conn


def _redact(url: str) -> str:
    """Hide password in connection string for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        redacted = parsed._replace(netloc=f"{parsed.username}:***@{parsed.hostname}:{parsed.port}")
        return urlunparse(redacted)
    except Exception:
        return "***"
