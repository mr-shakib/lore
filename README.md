# Lore

**The Organizational Memory Layer for AI-Native Companies**

Every time a human corrects an AI output, that correction disappears.  
Lore captures it, structures it, and feeds it back into every future AI call — automatically.

---

## What it does

AI tools like Copilot, Claude, and ChatGPT don't learn from your team's corrections. The same mistakes repeat: wrong tone, wrong terminology, decisions made last quarter ignored again. Lore fixes that.

- **Captures** every human correction of AI output (Slack edits, GitHub PR comments, in-app revisions)  
- **Mines** recurring patterns into behavioral rules using LLM-assisted clustering  
- **Injects** those rules, entity facts, and decisions into AI system prompts — before every generation  
- **Builds** a queryable organizational memory that improves with every correction

---

## Architecture

```
                    ┌─────────────────────────────┐
  Slack / GitHub → │  Event Capture API           │ → PostgreSQL (Supabase)
  Linear / Custom   │  POST /v1/events             │ → Redis (cache)
                    └──────────────┬──────────────┘
                                   │ (async, Kafka-ready)
                    ┌──────────────▼──────────────┐
                    │  Pattern Mining Engine       │ ← LLM (gpt-4o-mini)
                    │  Embeddings + clustering     │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Behavioral Rule Engine      │
                    │  Rule lifecycle management   │
                    └──────────────┬──────────────┘
                                   │
  AI Agent / SDK  ← ┌──────────────▼──────────────┐
                    │  Context Injection API       │
                    │  POST /v1/context            │
                    └─────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI 0.110 + uvicorn |
| Language | Python 3.11 |
| Database | PostgreSQL via Supabase (async SQLAlchemy + asyncpg) |
| Cache | Redis via Upstash (`rediss://` TLS) |
| Event queue | Kafka-ready (aiokafka) — disabled for MVP, `KAFKA_ENABLED=false` |
| Auth | Clerk (JWT middleware — M1 next) |
| Hosting | Render (Docker, Singapore region) |
| Validation | Pydantic v2 |
| Logging | structlog (JSON structured logs) |
| IDs | ULID (time-ordered, URL-safe) |

---

## Repository structure

```
lore/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/v1/           # Route handlers (events, context, rules, entities)
│   │   ├── services/         # Business logic (event capture, context graph, rule engine)
│   │   ├── models/           # Pydantic domain models
│   │   ├── database/         # PostgreSQL, Redis, Neo4j (stub) clients
│   │   ├── integrations/     # Webhook receivers (Slack, GitHub, Linear)
│   │   └── config.py         # pydantic-settings singleton
│   ├── migrations/
│   │   └── 001_initial.sql   # Full schema (7 tables)
│   ├── tests/                # pytest — 29/29 passing
│   ├── Dockerfile
│   └── pyproject.toml
└── render.yaml               # Render Blueprint (IaC)
```

---

## Local development

### Prerequisites

- Python 3.11+
- A [Supabase](https://supabase.com) project (free tier)
- An [Upstash Redis](https://upstash.com) database (free tier)

### Setup

```bash
# Clone
git clone https://github.com/mr-shakib/lore.git
cd lore

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
cd backend
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env — fill in DATABASE_URL, REDIS_URL
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://...` Supabase Transaction Pooler URL |
| `REDIS_URL` | ✅ | `rediss://...` Upstash Redis TLS URL |
| `SECRET_KEY` | ✅ | Random secret for signing |
| `KAFKA_ENABLED` | — | `false` (default) — enable when Kafka is provisioned |
| `ANTHROPIC_API_KEY` | M2 | For pattern mining LLM calls |
| `CLERK_SECRET_KEY` | M1 | For JWT auth middleware |

> **Note for Supabase users:** Use the Transaction Pooler URL (`aws-1-ap-southeast-1.pooler.supabase.com:6543`), not the direct connection. The direct connection is IPv6-only and fails on most local machines.

### Run database migrations

```bash
# Run once against your Supabase project
psql $DATABASE_URL -f migrations/001_initial.sql

# Or via Python (no psql required)
python -c "
import asyncio, asyncpg, ssl, pathlib
async def run():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(YOUR_DATABASE_URL, ssl=ssl_ctx)
    await conn.execute(pathlib.Path('migrations/001_initial.sql').read_text())
    print('Migration OK'); await conn.close()
asyncio.run(run())
"
```

### Start the server

```bash
# From repo root
python -m uvicorn app.main:app \
  --app-dir backend \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

### Run tests

```bash
cd backend
pytest -v --tb=short
# 29/29 passing
```

---

## API reference

### Health

```http
GET /v1/health
→ 200 {"status": "ok"}
```

### Capture a correction event

```http
POST /v1/events?workspace_id={workspace_id}
Content-Type: application/json

{
  "workspace_id": "ws_abc",
  "tool": "slack",
  "event_type": "correction",
  "actor_id": "actor_pseudonymized_hmac",
  "delta": [
    {
      "field": "message",
      "change_type": "tone",
      "change_summary": "Changed from formal to casual register"
    }
  ]
}

→ 202 {"event_id": "evt_01...", "status": "queued", ...}
```

### Request context injection

```http
POST /v1/context?workspace_id={workspace_id}
Content-Type: application/json

{
  "tool": "slack",
  "task": "Draft a message to the enterprise client about the delay",
  "entities": ["Acme Corp"],
  "max_tokens": 500
}

→ 200 {
  "context_id": "ctx_01...",
  "rules": [...],
  "entities": [...],
  "decisions": [...],
  "formatted_injection": "[LORE CONTEXT]\n..."
}
```

### Other endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/rules` | List active rules for a workspace |
| `POST` | `/v1/rules` | Create a rule manually |
| `PATCH` | `/v1/rules/{id}` | Confirm, edit, or dismiss a rule |
| `GET` | `/v1/entities` | List entity profiles |
| `POST` | `/v1/entities` | Create or update an entity |
| `POST` | `/integrations/slack/webhook` | Slack event webhook receiver |
| `POST` | `/integrations/github/webhook` | GitHub webhook receiver |
| `POST` | `/integrations/linear/webhook` | Linear webhook receiver |

Full interactive docs available at `/docs` (Swagger UI) and `/redoc`.

---

## Deployment

This repo ships with a `render.yaml` Blueprint.

1. Go to [dashboard.render.com](https://render.com) → **New → Blueprint**
2. Connect `github.com/mr-shakib/lore`
3. Render creates the `lore-api` web service from `backend/Dockerfile`
4. Add secrets in **Environment** tab: `DATABASE_URL`, `REDIS_URL`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`
5. Deploy — health check at `GET /v1/health`

---

## Privacy by design

Lore never stores raw AI outputs or message content. Only:
- Structured correction **deltas** (what field changed, how, summary of change)
- Pseudonymized actor IDs (HMAC — not reversible without the secret key)
- Metadata tags (tool, timestamp, context)

This makes Lore GDPR-friendly by default and safe for enterprise security reviews.

---

## Roadmap

| Milestone | Focus | Status |
|---|---|---|
| M1 | Backend backbone, event capture, Slack + GitHub webhooks | ✅ Complete |
| M2 | Pattern mining engine, behavioral rule engine, rule proposals | 🔜 Next |
| M3 | Context Injection API (full), Python + TypeScript SDK | 🔜 |
| M4 | Dashboard — decision log, entity memory, correction stream | 🔜 |
| M5 | SDK v1, design partner integrations, case studies | 🔜 |
| M6 | Neo4j graph DB (replaces PostgreSQL graph queries), retention | 🔜 |

---

## License

Private — all rights reserved.  
Contact: contactshakibhere@gmail.com
