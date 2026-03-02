"""
EntityService — persists entity profiles to PostgreSQL and syncs to Neo4j.

Auto-creation: called by the Pattern Mining Engine when an entity name
appears 3+ times in correction events.
Manual creation: available via the API for pre-seeding important entities.
"""

import json
from datetime import datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.entities import (
    Entity,
    EntityCreateRequest,
    EntityFact,
    EntityListResponse,
    EntityType,
    EntityUpdateRequest,
)

logger = structlog.get_logger(__name__)


class EntityService:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def list_entities(
        self,
        workspace_id: str,
        entity_type: EntityType | None = None,
        stale: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Entity], int]:
        offset = (page - 1) * page_size
        filters = "WHERE workspace_id = :ws"
        params: dict = {"ws": workspace_id, "limit": page_size, "offset": offset}

        if entity_type:
            filters += " AND entity_type = :entity_type"
            params["entity_type"] = entity_type.value
        if stale is not None:
            filters += " AND is_stale = :stale"
            params["stale"] = stale

        count_result = await self.conn.execute(
            text(f"SELECT COUNT(*) FROM entities {filters}"), params
        )
        total: int = count_result.scalar_one()

        rows = await self.conn.execute(
            text(
                f"SELECT * FROM entities {filters} ORDER BY last_updated DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        items = [self._row_to_entity(dict(r)) for r in rows.mappings()]
        return items, total

    async def get_entity(self, entity_id: str) -> Entity | None:
        result = await self.conn.execute(
            text("SELECT * FROM entities WHERE entity_id = :id"), {"id": entity_id}
        )
        row = result.mappings().first()
        return self._row_to_entity(dict(row)) if row else None

    async def find_by_name(self, workspace_id: str, name: str) -> Entity | None:
        """Case-insensitive lookup — used for duplicate detection."""
        result = await self.conn.execute(
            text(
                "SELECT * FROM entities WHERE workspace_id = :ws AND name_lower = :name_lower"
            ),
            {"ws": workspace_id, "name_lower": name.lower().strip()},
        )
        row = result.mappings().first()
        return self._row_to_entity(dict(row)) if row else None

    async def create_entity(self, body: EntityCreateRequest) -> Entity:
        # Dedup check
        existing = await self.find_by_name(body.workspace_id, body.name)
        if existing:
            logger.info("entity_already_exists", entity_id=existing.entity_id, name=body.name)
            return existing

        entity = Entity(
            workspace_id=body.workspace_id,
            name=body.name,
            entity_type=body.entity_type,
            facts=body.facts,
            is_permanently_relevant=body.is_permanently_relevant,
        )

        await self.conn.execute(
            text(
                """
                INSERT INTO entities (
                    entity_id, workspace_id, name, name_lower, entity_type, facts,
                    is_stale, is_permanently_relevant, mention_count, created_at, last_updated
                ) VALUES (
                    :entity_id, :workspace_id, :name, :name_lower, :entity_type, :facts,
                    :is_stale, :is_permanently_relevant, :mention_count, :created_at, :last_updated
                )
                """
            ),
            {
                "entity_id": entity.entity_id,
                "workspace_id": entity.workspace_id,
                "name": entity.name,
                "name_lower": entity.name.lower().strip(),
                "entity_type": entity.entity_type.value,
                "facts": json.dumps([f.model_dump() for f in entity.facts]),
                "is_stale": entity.is_stale,
                "is_permanently_relevant": entity.is_permanently_relevant,
                "mention_count": entity.mention_count,
                "created_at": entity.created_at,
                "last_updated": entity.last_updated,
            },
        )
        await self.conn.commit()

        await self._sync_entity_to_graph(entity)
        return entity

    async def update_entity(self, entity_id: str, body: EntityUpdateRequest) -> Entity | None:
        existing = await self.get_entity(entity_id)
        if not existing:
            return None

        updates: dict = {}
        if body.facts is not None:
            updates["facts"] = json.dumps([f.model_dump() for f in body.facts])
        if body.is_permanently_relevant is not None:
            updates["is_permanently_relevant"] = body.is_permanently_relevant
        if body.entity_type is not None:
            updates["entity_type"] = body.entity_type.value
        updates["last_updated"] = datetime.utcnow()

        if updates:
            set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
            updates["id"] = entity_id
            await self.conn.execute(
                text(f"UPDATE entities SET {set_clauses} WHERE entity_id = :id"), updates
            )
            await self.conn.commit()

        return await self.get_entity(entity_id)

    async def mark_stale(self, entity_id: str) -> bool:
        result = await self.conn.execute(
            text(
                "UPDATE entities SET is_stale = true WHERE entity_id = :id AND is_permanently_relevant = false RETURNING entity_id"
            ),
            {"id": entity_id},
        )
        await self.conn.commit()
        return result.rowcount > 0

    # ── Graph sync ────────────────────────────────────────────────────────────

    async def _sync_entity_to_graph(self, entity: Entity) -> None:
        """
        Graph sync — no-op for MVP (Neo4j deferred to M6).
        Entities are queried directly from PostgreSQL by ContextGraphService.
        """
        logger.debug("entity_graph_sync_skipped", entity_id=entity.entity_id, reason="postgres_only_mvp")

    # ── Row mapper ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_col(value, default):
        if value is None:
            return default
        if isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _row_to_entity(row: dict) -> Entity:
        raw_facts = EntityService._parse_json_col(row.get("facts"), [])
        row["facts"] = [EntityFact(**f) if isinstance(f, dict) else f for f in raw_facts]
        row.setdefault("linked_corrections", [])
        row.setdefault("linked_decisions", [])
        row.setdefault("linked_rules", [])
        return Entity(**row)
