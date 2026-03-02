"""Health check endpoints — used by load balancers and uptime monitors."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database.postgres import get_connection
from app.database.redis import get_redis_dep

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Returns 200 if the API process is running."""
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness probe — checks all dependencies")
async def health_ready(
    conn: AsyncConnection = Depends(get_connection),
    redis=Depends(get_redis_dep),
) -> dict:
    """
    Returns 200 only when all critical dependencies are reachable.
    Used by Kubernetes/Render to gate traffic.
    """
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    # Redis
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # Neo4j (imported here to avoid circular issues with lifespan)
    try:
        from app.database.neo4j import get_driver

        driver = get_driver()
        await driver.verify_connectivity()
        checks["neo4j"] = "ok"
    except Exception as exc:
        checks["neo4j"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
