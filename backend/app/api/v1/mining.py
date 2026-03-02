"""
Mining API — manually trigger or inspect the Pattern Mining Engine.

POST /v1/mining/run  — trigger one mining pass immediately (admin use / testing)

This endpoint is useful during development and design partner onboarding to
run pattern mining on demand rather than waiting for the scheduled 6-hour window.
In production, the APScheduler background job runs automatically.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database.postgres import get_connection
from app.services.pattern_mining import PatternMiningService
from app.services.rule_engine import RuleEngineService

logger = structlog.get_logger(__name__)
router = APIRouter()


class MiningRunResponse(BaseModel):
    workspaces_processed: int
    events_processed: int
    proposals_created: int
    message: str


class ExpiryCheckResponse(BaseModel):
    rules_flagged: int
    message: str


@router.post(
    "/run",
    response_model=MiningRunResponse,
    summary="Trigger an immediate pattern mining pass",
    description=(
        "Runs the pattern mining engine now across all workspaces with unprocessed events. "
        "Normally this runs automatically every 6 hours. Use this endpoint to trigger it "
        "manually during testing or onboarding. Requires GROQ_API_KEY to generate proposals."
    ),
)
async def run_mining(
    conn: AsyncConnection = Depends(get_connection),
) -> MiningRunResponse:
    try:
        service = PatternMiningService(conn)
        stats = await service.run_mining_pass()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    proposals = stats["proposals_created"]
    events = stats["events_processed"]
    return MiningRunResponse(
        **stats,
        message=(
            f"Mining complete. Processed {events} event(s) across "
            f"{stats['workspaces_processed']} workspace(s). "
            f"Created {proposals} new rule proposal(s)."
            if events > 0
            else "No unprocessed events found. Nothing to mine."
        ),
    )


@router.post(
    "/expire-check",
    response_model=ExpiryCheckResponse,
    summary="Trigger rule expiry check",
    description=(
        "Finds active rules with no supporting evidence for 90+ days and marks them "
        "as 'needs_review'. Normally runs automatically every 24 hours. "
        "Use this endpoint to trigger an immediate check during testing or admin workflows. "
        "Rules flagged as 'needs_review' are excluded from context injection until an admin "
        "reviews and re-activates or archives them via PATCH /v1/rules/{rule_id}."
    ),
)
async def run_expire_check(
    conn: AsyncConnection = Depends(get_connection),
) -> ExpiryCheckResponse:
    service = RuleEngineService(conn)
    count = await service.expire_stale_rules(days=90)
    return ExpiryCheckResponse(
        rules_flagged=count,
        message=(
            f"Expiry check complete. {count} rule(s) transitioned to 'needs_review'."
            if count > 0
            else "No stale rules found. All active rules have recent supporting evidence."
        ),
    )
