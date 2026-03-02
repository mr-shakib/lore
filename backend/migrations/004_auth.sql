-- ============================================================
-- Lore — M3: Auth tables (users + api_keys)
-- Migration: 004_auth
-- Run with: psql $DATABASE_URL -f migrations/004_auth.sql
-- ============================================================

-- ── Users ─────────────────────────────────────────────────────────────────────
-- id = Clerk user ID (user_xxx) — primary key, no auto-generation needed.
-- workspace_id references the workspaces table.

CREATE TABLE IF NOT EXISTS users (
    id              TEXT        PRIMARY KEY,          -- Clerk sub claim  (user_xxx)
    workspace_id    TEXT        NOT NULL
                        REFERENCES workspaces (workspace_id) ON DELETE CASCADE,
    email           TEXT        NOT NULL,
    role            TEXT        NOT NULL DEFAULT 'member',   -- admin | member | viewer
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_workspace
    ON users (workspace_id);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON users (email);

COMMENT ON TABLE users IS
    'Human users authenticated via Clerk. id = Clerk sub claim.';

COMMENT ON COLUMN users.role IS
    'admin — can manage workspace settings and API keys; '
    'member — can view and confirm rules; '
    'viewer — read-only access.';

-- ── API Keys ───────────────────────────────────────────────────────────────────
-- Plaintext keys (sk-lore-xxx) are NEVER stored.
-- key_hash = SHA-256 of the raw key; used for look-up at auth time.

CREATE TABLE IF NOT EXISTS api_keys (
    id              TEXT        PRIMARY KEY,           -- key_xxx (ULID)
    workspace_id    TEXT        NOT NULL
                        REFERENCES workspaces (workspace_id) ON DELETE CASCADE,
    key_hash        TEXT        NOT NULL UNIQUE,       -- SHA-256(raw_key)
    name            TEXT        NOT NULL,              -- human label
    scopes          TEXT[]      NOT NULL DEFAULT ARRAY['read', 'write'],
    created_by      TEXT,                              -- Clerk user id (nullable — bootstrap keys)
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_workspace
    ON api_keys (workspace_id);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash
    ON api_keys (key_hash);

COMMENT ON TABLE api_keys IS
    'SDK / automation API keys. Only SHA-256 hashes stored — plaintext shown once at creation.';

COMMENT ON COLUMN api_keys.key_hash IS
    'SHA-256 hex digest of the raw sk-lore-xxx key. Used for constant-time look-up.';
