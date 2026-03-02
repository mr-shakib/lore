-- ============================================================
-- Lore — Migration 002: Add pg_trgm extension
-- Run in Supabase SQL Editor before deploying M2.
-- This extension is built into PostgreSQL — no extra cost.
-- ============================================================

-- pg_trgm enables trigram-based text similarity searches.
-- Used by pattern mining for optional SQL-side similarity queries.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
