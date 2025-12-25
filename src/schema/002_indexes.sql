-- =============================================================================
-- INDEXES FOR PG-AUTHZ
-- =============================================================================
-- Optimized for lazy evaluation with recursive CTEs.
-- =============================================================================
-- TUPLES INDEXES
-- =============================================================================
-- Primary lookup: find grants on a specific resource
CREATE INDEX tuples_resource_grants_idx ON authz.tuples (namespace, resource_type, resource_id, relation);

-- Find what groups/resources a subject belongs to (for recursive expansion)
CREATE INDEX tuples_subject_memberships_idx ON authz.tuples (namespace, subject_type, subject_id, relation);

-- Note: tuples_unique_idx (defined in 001_tables.sql) covers queries needing
-- (namespace, resource_type, resource_id, relation, subject_type, subject_id).
-- A separate tuples_group_members_idx is not needed and was removed to avoid
-- redundant storage and write overhead.

-- Expiration lookup for cleanup queries (partial index)
CREATE INDEX tuples_expires_at_idx ON authz.tuples (namespace, expires_at)
WHERE
    expires_at IS NOT NULL;

-- =============================================================================
-- PERMISSION HIERARCHY INDEXES
-- =============================================================================
-- Lookup: what does this permission imply?
CREATE INDEX permission_hierarchy_lookup_idx ON authz.permission_hierarchy (namespace, resource_type, permission);

-- Reverse lookup: what permissions imply this one?
CREATE INDEX permission_hierarchy_reverse_idx ON authz.permission_hierarchy (namespace, resource_type, implies);
