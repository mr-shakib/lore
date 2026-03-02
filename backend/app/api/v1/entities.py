"""
Entities API — manages the Entity Memory System.

GET  /v1/entities              — list entities for a workspace
GET  /v1/entities/{entity_id}  — get a single entity
POST /v1/entities              — manually create an entity
PATCH /v1/entities/{entity_id} — update entity facts or flags
DELETE /v1/entities/{entity_id} — soft-delete (marks as stale)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database.postgres import get_connection
from app.models.entities import (
    Entity,
    EntityCreateRequest,
    EntityListResponse,
    EntityType,
    EntityUpdateRequest,
)
from app.services.entity_service import EntityService

router = APIRouter()


@router.get("", response_model=EntityListResponse, summary="List entities for a workspace")
async def list_entities(
    workspace_id: str,
    entity_type: EntityType | None = None,
    stale: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: AsyncConnection = Depends(get_connection),
) -> EntityListResponse:
    service = EntityService(conn)
    items, total = await service.list_entities(
        workspace_id,
        entity_type=entity_type,
        stale=stale,
        page=page,
        page_size=page_size,
    )
    return EntityListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{entity_id}", response_model=Entity, summary="Get entity by ID")
async def get_entity(
    entity_id: str,
    conn: AsyncConnection = Depends(get_connection),
) -> Entity:
    service = EntityService(conn)
    entity = await service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id!r} not found.")
    return entity


@router.post(
    "",
    response_model=Entity,
    status_code=status.HTTP_201_CREATED,
    summary="Manually create an entity",
)
async def create_entity(
    body: EntityCreateRequest,
    conn: AsyncConnection = Depends(get_connection),
) -> Entity:
    service = EntityService(conn)
    return await service.create_entity(body)


@router.patch("/{entity_id}", response_model=Entity, summary="Update entity facts or flags")
async def update_entity(
    entity_id: str,
    body: EntityUpdateRequest,
    conn: AsyncConnection = Depends(get_connection),
) -> Entity:
    service = EntityService(conn)
    updated = await service.update_entity(entity_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id!r} not found.")
    return updated


@router.delete(
    "/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete entity (marks as stale)",
)
async def delete_entity(
    entity_id: str,
    conn: AsyncConnection = Depends(get_connection),
) -> None:
    service = EntityService(conn)
    ok = await service.mark_stale(entity_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id!r} not found.")
