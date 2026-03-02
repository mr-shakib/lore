"""
Settings — loaded from environment variables / .env file.
All secrets live here. Never import raw os.environ elsewhere.
"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env relative to the backend/ directory regardless of cwd
_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "Lore API"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production", "testing"] = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # ── PostgreSQL (Supabase) ─────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lore"

    # ── Neo4j (AuraDB) ────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    # ── Upstash Redis ─────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── Kafka ─────────────────────────────────────────────────────────────────────
    kafka_enabled: bool = False    # Set to true once Kafka is provisioned
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_username: str | None = None
    kafka_password: str | None = None
    kafka_use_sasl: bool = False
    kafka_topic_events: str = "lore.events"
    kafka_topic_corrections: str = "lore.corrections"
    kafka_consumer_group: str = "lore-backend"

    # ── LLM ───────────────────────────────────────────────────────────────────
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    pattern_mining_model: str = "gpt-4o-mini"
    context_injection_model: str = "claude-3-haiku-20240307"

    # ── Auth (Clerk) ──────────────────────────────────────────────────────────
    clerk_secret_key: str | None = None
    clerk_publishable_key: str | None = None
    clerk_webhook_secret: str | None = None

    # ── Integrations ──────────────────────────────────────────────────────────
    slack_signing_secret: str | None = None
    slack_bot_token: str | None = None
    linear_webhook_secret: str | None = None
    github_webhook_secret: str | None = None

    # ── Rate limits ───────────────────────────────────────────────────────────
    event_rate_limit_per_workspace: int = 1000   # events/minute
    context_api_rate_limit: int = 100             # requests/minute per workspace

    # ── Derived helpers ───────────────────────────────────────────────────────
    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure the driver prefix is asyncpg-compatible."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def kafka_sasl_config(self) -> dict | None:
        """Returns aiokafka SASL config dict if SASL is enabled."""
        if not self.kafka_use_sasl:
            return None
        return {
            "security_protocol": "SASL_SSL",
            "sasl_mechanism": "SCRAM-SHA-256",
            "sasl_plain_username": self.kafka_username,
            "sasl_plain_password": self.kafka_password,
        }


# Single shared instance — import this everywhere
settings = Settings()
