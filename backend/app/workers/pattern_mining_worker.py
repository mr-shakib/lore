"""
Pattern Mining Background Worker — runs on a scheduled interval via APScheduler.

The scheduler is started during the FastAPI app lifespan (after DB init)
and stopped cleanly on shutdown.

Jobs:
  - pattern_mining   : runs every N hours (default: 6) to cluster correction events
                       and generate rule proposals via Groq LLM.
  - rule_expiry_check: runs daily to mark stale rules as 'needs_review' when they
                       have had no supporting evidence for 90+ days.

The worker acquires its own DB connection for each run so it does not
compete with request-handling connections from the connection pool.
"""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database.postgres import get_engine
from app.services.pattern_mining import PatternMiningService
from app.services.rule_engine import RuleEngineService

logger = structlog.get_logger(__name__)

_scheduler = AsyncIOScheduler()


async def _run_mining_job() -> None:
    """
    APScheduler job function.
    Gets its own short-lived DB connection — closed after each run.
    Never raises: failures are logged and swallowed so the scheduler keeps running.
    """
    logger.info("pattern_mining_job_started")
    try:
        async with get_engine().connect() as conn:
            service = PatternMiningService(conn)
            stats = await service.run_mining_pass()
            logger.info("pattern_mining_job_complete", **stats)
    except Exception:
        logger.exception("pattern_mining_job_failed")


async def _run_expiry_check_job() -> None:
    """
    Daily APScheduler job — finds active rules idle for 90+ days and
    transitions them to 'needs_review' so an admin can verify they are still valid.

    Never raises: failures are logged and swallowed.
    """
    logger.info("rule_expiry_check_job_started")
    try:
        async with get_engine().connect() as conn:
            service = RuleEngineService(conn)
            count = await service.expire_stale_rules(days=90)
            logger.info("rule_expiry_check_job_complete", rules_flagged=count)
    except Exception:
        logger.exception("rule_expiry_check_job_failed")


def start_scheduler() -> None:
    """
    Register and start the background scheduler.
    Called from the FastAPI lifespan context manager after DB init.
    """
    _scheduler.add_job(
        _run_mining_job,
        trigger="interval",
        hours=settings.pattern_mining_interval_hours,
        id="pattern_mining",
        replace_existing=True,
        max_instances=1,  # Never run two passes simultaneously
    )

    _scheduler.add_job(
        _run_expiry_check_job,
        trigger="interval",
        hours=24,          # Daily
        id="rule_expiry_check",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "pattern_mining_scheduler_started",
        interval_hours=settings.pattern_mining_interval_hours,
        expiry_check_interval_hours=24,
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler. Called from the FastAPI lifespan."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("pattern_mining_scheduler_stopped")
