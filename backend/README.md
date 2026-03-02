# Lore Backend

**The organizational memory layer for AI-native companies.**

FastAPI backend — event capture, Company Context Graph, context injection API, behavioral rule engine.

---

## Stack

| Layer | Service | Notes |
|---|---|---|
| Framework | FastAPI + uvicorn | Async-native, auto OpenAPI docs |
| PostgreSQL | Supabase Free (local: Docker) | Structured event log + rule metadata |
| Graph DB | Neo4j AuraDB Free (local: Docker) | Company Context Graph |
| Cache / KV | Upstash Redis Free (local: Docker) | Context cache, rate limiting, dedup |
| Event stream | Upstash Kafka Free (local: Redpanda) | Async pattern mining pipeline |
| Auth | Clerk | JWT verification + workspace management |

---

## Local Setup (5 minutes)

### 1. Prerequisites
- Python 3.11+
- Docker Desktop (for local services)

### 2. Clone and install

```bash
cd backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -e ".[dev]"
```

### 3. Environment variables

```bash
cp .env.example .env
# Edit .env — defaults work for local Docker, no changes needed to start
```

### 4. Start local services (PostgreSQL, Neo4j, Redis, Kafka)

```bash
docker compose up -d postgres neo4j redis kafka
```

Wait ~30 seconds for all services to be healthy:
```bash
docker compose ps   # All should show "healthy"
```

### 5. Run the API

```bash
uvicorn app.main:app --reload
```

API is now running at **http://localhost:8000**

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Neo4j Browser:** http://localhost:7474 (user: neo4j / password: password)

---

## How to Test

### Run all unit tests (no DB required)

```bash
pytest -m "not integration" -v
```

### Run with coverage

```bash
pytest -m "not integration" --cov=app --cov-report=term-missing
```

### Run integration tests (requires local Docker services running)

```bash
pytest -v
```

### Test the API manually

**Health check:**
```bash
curl http://localhost:8000/v1/health
```

**Ingest a correction event:**
```bash
curl -X POST http://localhost:8000/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "ws_local_dev",
    "tool": "slack",
    "event_type": "correction",
    "actor_id": "actor_test_abc",
    "ai_output_id": "out_test_001",
    "context_tags": {"channel": "general", "customer_tier": "enterprise"},
    "delta": [{
      "field": "message_content",
      "change_type": "tone",
      "change_summary": "Changed tone from informal to formal"
    }],
    "confidence_signal": 0.9
  }'
```
Expected: `{"event_id": "evt_...", "status": "queued", ...}`

**Request context injection:**
```bash
curl -X POST "http://localhost:8000/v1/context?workspace_id=ws_local_dev" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "email-agent",
    "task": "Draft a follow-up email",
    "entities": [],
    "context_tags": {"customer_tier": "enterprise"},
    "max_rules": 5
  }'
```
Expected: `{"context_id": "ctx_...", "rules": [], "formatted_injection": "[LORE CONTEXT]", ...}`

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app factory + lifespan
│   ├── config.py            # All settings (pydantic-settings)
│   ├── database/
│   │   ├── postgres.py      # Async SQLAlchemy engine
│   │   ├── neo4j.py         # Neo4j async driver + schema bootstrap
│   │   └── redis.py         # Redis async client + cache helpers
│   ├── models/
│   │   ├── events.py        # CaptureEvent, CaptureEventCreate
│   │   ├── context.py       # ContextRequest, ContextResponse
│   │   ├── rules.py         # Rule, RuleProposal
│   │   └── entities.py      # Entity, EntityFact
│   ├── api/v1/
│   │   ├── health.py        # GET /v1/health, /v1/health/ready
│   │   ├── events.py        # POST /v1/events
│   │   ├── context.py       # POST /v1/context
│   │   ├── rules.py         # CRUD /v1/rules + proposals
│   │   ├── entities.py      # CRUD /v1/entities
│   │   └── webhooks.py      # Mounts integration routers
│   ├── services/
│   │   ├── event_capture.py  # Persist events to Postgres + Kafka
│   │   ├── context_graph.py  # Query Neo4j for context assembly
│   │   ├── rule_engine.py    # Rule lifecycle + proposal management
│   │   ├── entity_service.py # Entity CRUD + auto-creation
│   │   └── kafka_producer.py # Async Kafka producer (optional)
│   └── integrations/
│       ├── slack.py          # Slack Events API webhook
│       ├── github.py         # GitHub App webhook
│       └── linear.py         # Linear webhook
├── migrations/
│   └── 001_initial.sql      # Full PostgreSQL schema
├── tests/
│   ├── conftest.py          # Shared fixtures + app client
│   ├── test_events.py       # Event capture tests
│   └── test_context.py      # Context injection tests
├── docker-compose.yml       # Local dev services
├── Dockerfile               # Production container
├── pyproject.toml           # Dependencies + tool config
└── .env.example             # All environment variables documented
```

---

## API Reference

Full interactive docs at http://localhost:8000/docs when running locally.

| Method | Path | Description |
|---|---|---|
| GET | `/v1/health` | Liveness probe |
| GET | `/v1/health/ready` | Readiness probe (checks all dependencies) |
| POST | `/v1/events` | Ingest a correction event |
| GET | `/v1/events` | List events for a workspace |
| GET | `/v1/events/{event_id}` | Get a single event |
| POST | `/v1/context` | **Core endpoint** — fetch context for AI injection |
| GET | `/v1/rules` | List rules |
| GET | `/v1/rules/proposals` | List pending rule proposals |
| POST | `/v1/rules/proposals/{id}/confirm` | Confirm a rule proposal |
| POST | `/v1/rules/proposals/{id}/dismiss` | Dismiss a rule proposal |
| PATCH | `/v1/rules/{rule_id}` | Update a rule |
| GET | `/v1/entities` | List entities |
| POST | `/v1/entities` | Manually create an entity |
| PATCH | `/v1/entities/{entity_id}` | Update entity facts |
| POST | `/v1/webhooks/slack` | Slack Events API receiver |
| POST | `/v1/webhooks/github` | GitHub App webhook receiver |
| POST | `/v1/webhooks/linear` | Linear webhook receiver |

---

## What's Next (MVP Week 3–8)

- [ ] Pattern Mining Engine (background service, cluster correction events, propose rules via LLM)
- [ ] Populate Neo4j on event ingestion (entity auto-extraction from context_tags)
- [ ] Alembic migrations (for production schema management)
- [ ] Clerk JWT middleware (authenticate all `/v1/` requests)
- [ ] Kafka consumer (async event processor for pattern mining)
- [ ] SDK v1 (Python + TypeScript, 3-line integration)
- [ ] Correction Stream WebSocket endpoint
- [ ] Founder Digest email generation (weekly Resend integration)
