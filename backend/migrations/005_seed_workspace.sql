-- ============================================================
-- Lore — Migration 005: Seed the production workspace
-- Run with: psql $DATABASE_URL -f migrations/005_seed_workspace.sql
--
-- Migration 001 only seeded 'ws_local_dev' for local dev.
-- The auth middleware and bootstrap endpoint default to
-- 'ws_01jng0q5xze7v4g7xp64cj3vxh' — insert it here so new
-- users can be auto-assigned and create API keys without a
-- FK violation.
-- ============================================================

INSERT INTO workspaces (workspace_id, name, plan)
VALUES ('ws_01jng0q5xze7v4g7xp64cj3vxh', 'Default Workspace', 'starter')
ON CONFLICT (workspace_id) DO NOTHING;
