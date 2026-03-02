"""
Kafka producer — publishes correction events to the lore.corrections topic
for async processing by the Pattern Mining Engine.

Uses aiokafka with SASL/SCRAM for Upstash Kafka (production) or plain text
for local development.

The producer is optional at MVP stage — if Kafka is not configured,
events are stored in PostgreSQL only.
"""

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from app.config import settings

logger = structlog.get_logger(__name__)

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer | None:
    """
    Returns the shared Kafka producer, initializing it on first call.
    Returns None if Kafka is not configured (allows graceful degradation).
    """
    global _producer

    if not settings.kafka_enabled:
        return None  # Fast path — no connection attempt, no timeout

    # Dev/test shortcut: local Kafka with no SASL
    if _producer:
        return _producer

    try:
        kwargs: dict = {
            "bootstrap_servers": settings.kafka_bootstrap_servers,
            "value_serializer": None,   # We serialize to bytes before calling send
            "compression_type": "gzip",
            "max_batch_size": 16384,
            "linger_ms": 5,             # 5ms batching window — keeps throughput high
        }

        sasl = settings.kafka_sasl_config
        if sasl:
            kwargs.update(
                security_protocol=sasl["security_protocol"],
                sasl_mechanism=sasl["sasl_mechanism"],
                sasl_plain_username=sasl["sasl_plain_username"],
                sasl_plain_password=sasl["sasl_plain_password"],
            )

        _producer = AIOKafkaProducer(**kwargs)
        await _producer.start()
        logger.info("kafka_producer_started", servers=settings.kafka_bootstrap_servers)

    except KafkaError as exc:
        logger.warning(
            "kafka_producer_unavailable",
            reason=str(exc),
            note="Events will be stored in PostgreSQL only",
        )
        _producer = None

    return _producer


async def stop_producer() -> None:
    """Graceful shutdown — called from app lifespan if producer was started."""
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("kafka_producer_stopped")
