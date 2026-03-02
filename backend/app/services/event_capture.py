"""
EventCaptureService — persists correction events to PostgreSQL
and queues them for async processing by the Pattern Mining Engine.

Storage:
  - PostgreSQL: structured event record (fast writes, queryable log)
  - Kafka: event message for async downstream processing

The service uses raw SQL (SQLAlchemy Core) for explicit control and
async compatibility.
"""

import json
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.events import CaptureEvent, CaptureEventCreate

logger = structlog.get_logger(__name__)

# Kafka producer is optional — if not configured, events are stored only in Postgres
_kafka_producer = None


class EventCaptureService:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def ingest(self, payload: CaptureEventCreate) -> CaptureEvent:
        """
        Persist an inbound event to PostgreSQL and publish to Kafka.
        Returns the fully-formed CaptureEvent with its generated ID.
        """
        event = CaptureEvent(**payload.model_dump())

        await self._insert_event(event)

        # Fire-and-forget to Kafka (non-blocking)
        await self._publish_to_kafka(event)

        return event

    async def get_by_id(self, event_id: str) -> CaptureEvent | None:
        result = await self.conn.execute(
            text("SELECT * FROM correction_events WHERE event_id = :event_id"),
            {"event_id": event_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return self._row_to_event(dict(row))

    async def list_events(
        self,
        workspace_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CaptureEvent], int]:
        offset = (page - 1) * page_size

        count_result = await self.conn.execute(
            text("SELECT COUNT(*) FROM correction_events WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        )
        total = count_result.scalar_one()

        rows_result = await self.conn.execute(
            text(
                """
                SELECT * FROM correction_events
                WHERE workspace_id = :ws
                ORDER BY timestamp DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"ws": workspace_id, "limit": page_size, "offset": offset},
        )
        items = [self._row_to_event(dict(r)) for r in rows_result.mappings()]
        return items, total

    # ── Private ───────────────────────────────────────────────────────────────

    async def _insert_event(self, event: CaptureEvent) -> None:
        await self.conn.execute(
            text(
                """
                INSERT INTO correction_events (
                    event_id, workspace_id, tool, event_type, actor_id,
                    ai_output_id, context_tags, delta, confidence_signal,
                    session_id, external_ref, timestamp, processed
                ) VALUES (
                    :event_id, :workspace_id, :tool, :event_type, :actor_id,
                    :ai_output_id, :context_tags, :delta, :confidence_signal,
                    :session_id, :external_ref, :timestamp, :processed
                )
                ON CONFLICT (event_id) DO NOTHING
                """
            ),
            {
                "event_id": event.event_id,
                "workspace_id": event.workspace_id,
                "tool": event.tool.value,
                "event_type": event.event_type.value,
                "actor_id": event.actor_id,
                "ai_output_id": event.ai_output_id,
                "context_tags": json.dumps(event.context_tags),
                "delta": json.dumps([d.model_dump() for d in event.delta]),
                "confidence_signal": event.confidence_signal,
                "session_id": event.session_id,
                "external_ref": event.external_ref,
                "timestamp": event.timestamp,
                "processed": event.processed,
            },
        )
        await self.conn.commit()
        logger.debug("event_inserted", event_id=event.event_id)

    async def _publish_to_kafka(self, event: CaptureEvent) -> None:
        """Publish the event to Kafka for async pattern mining. Silently skips if Kafka is not configured."""
        try:
            from app.services.kafka_producer import get_producer

            producer = await get_producer()
            if producer:
                await producer.send_and_wait(
                    "lore.corrections",
                    value=event.model_dump_json().encode(),
                    key=event.workspace_id.encode(),
                )
        except Exception as exc:
            # Kafka is optional at MVP stage — log but never fail the ingest
            logger.warning("kafka_publish_skipped", reason=str(exc), event_id=event.event_id)

    @staticmethod
    def _row_to_event(row: dict) -> CaptureEvent:
        """Convert a database row dict to a CaptureEvent model instance."""
        row["context_tags"] = json.loads(row["context_tags"]) if row.get("context_tags") else {}
        row["delta"] = json.loads(row["delta"]) if row.get("delta") else []
        return CaptureEvent(**row)
