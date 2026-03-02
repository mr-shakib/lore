-- ============================================================
-- Lore — M2: Rule Conflict Detection + Expiry Checker
-- Migration: 003_m2_conflict_expiry
-- Run with: psql $DATABASE_URL -f migrations/003_m2_conflict_expiry.sql
-- ============================================================

-- ── Conflict tracking on rules ─────────────────────────────────────────────
-- conflict_with: JSON array of rule_ids that this rule conflicts with
-- When two rules semantically oppose each other, both are set to status='conflict'
-- and each lists the other in conflict_with.

ALTER TABLE rules
    ADD COLUMN IF NOT EXISTS conflict_with JSONB NOT NULL DEFAULT '[]';

-- Index: fast lookup of all rules currently in a conflict state
CREATE INDEX IF NOT EXISTS idx_rules_conflict
    ON rules (workspace_id) WHERE status = 'conflict';

-- Index: fast lookup of rules needing review (stale rules)
CREATE INDEX IF NOT EXISTS idx_rules_needs_review
    ON rules (workspace_id) WHERE status = 'needs_review';

-- Comment on new status values (informational, not enforced by DB):
-- 'needs_review'  — active rule has not seen supporting evidence in 90+ days
-- 'conflict'      — rule semantically opposes another active rule in the same workspace
COMMENT ON COLUMN rules.status IS
    'proposed | active | paused | deprecated | archived | needs_review | conflict';

COMMENT ON COLUMN rules.conflict_with IS
    'JSON array of rule_ids that this rule conflicts with. Set during conflict detection on confirm.';

COMMENT ON COLUMN rules.last_supported IS
    'Timestamp of the most recent mining pass that found evidence supporting this rule''s scope. '
    'Null = never refreshed after initial confirmation. Drives expiry checker.';
