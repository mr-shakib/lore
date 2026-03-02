"""
Rules API — manages the Behavioral Rule Engine's rule lifecycle.

GET  /v1/rules              — list all rules for a workspace
GET  /v1/rules/{rule_id}    — get a single rule
PATCH /v1/rules/{rule_id}   — update a rule (text, scope, status)
DELETE /v1/rules/{rule_id}  — archive a rule

Rule proposals are at /v1/proposals (separate router — avoids wildcard conflicts).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database.postgres import get_connection
from app.models.rules import (
    Rule,
    RuleConfirmRequest,
    RuleListResponse,
    RuleProposal,
    RuleStatus,
    RuleUpdateRequest,
)
from app.services.rule_engine import RuleEngineService

router = APIRouter()


@router.get("", response_model=RuleListResponse, summary="List rules for a workspace")
async def list_rules(
    workspace_id: str,
    status: RuleStatus | None = None,
    tool: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: AsyncConnection = Depends(get_connection),
) -> RuleListResponse:
    service = RuleEngineService(conn)
    items, total = await service.list_rules(
        workspace_id, status=status, tool=tool, page=page, page_size=page_size
    )
    return RuleListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{rule_id}", response_model=Rule, summary="Get a rule by ID")
async def get_rule(
    rule_id: str,
    conn: AsyncConnection = Depends(get_connection),
) -> Rule:
    service = RuleEngineService(conn)
    rule = await service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found.")
    return rule


@router.patch("/{rule_id}", response_model=Rule, summary="Update a rule")
async def update_rule(
    rule_id: str,
    body: RuleUpdateRequest,
    conn: AsyncConnection = Depends(get_connection),
) -> Rule:
    service = RuleEngineService(conn)
    updated = await service.update_rule(rule_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found.")
    return updated


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Archive a rule")
async def archive_rule(
    rule_id: str,
    conn: AsyncConnection = Depends(get_connection),
) -> None:
    service = RuleEngineService(conn)
    ok = await service.archive_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found.")
