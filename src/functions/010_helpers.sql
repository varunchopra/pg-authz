-- =============================================================================
-- INTERNAL HELPERS
-- =============================================================================
-- Reusable functions used by multiple core operations. These are internal
-- (prefixed with _ or named generically) and not part of the public API.


-- Expand user memberships recursively
--
-- Given a user, returns all groups they belong to, including nested groups.
-- Used by check, list_resources, and filter_authorized to avoid duplicating
-- the same recursive CTE logic.
--
-- Example: If alice is in team:infra, and team:infra is in team:platform,
-- this returns both (team, infra, member) and (team, platform, member).
--
-- Note: list_users expands in the opposite direction (from resource down to
-- users) so it can't use this function.
CREATE OR REPLACE FUNCTION authz._expand_user_memberships(
    p_user_id text,
    p_namespace text DEFAULT 'default'
)
RETURNS TABLE(group_type text, group_id text, membership_relation text)
AS $$
    WITH RECURSIVE user_memberships AS (
        -- Direct memberships
        SELECT
            resource_type AS group_type,
            resource_id AS group_id,
            relation AS membership_relation,
            1 AS depth
        FROM authz.tuples
        WHERE namespace = p_namespace
          AND subject_type = 'user'
          AND subject_id = p_user_id
          AND (expires_at IS NULL OR expires_at > now())

        UNION

        -- Nested: groups containing groups the user is in
        SELECT
            t.resource_type,
            t.resource_id,
            t.relation,
            um.depth + 1
        FROM user_memberships um
        JOIN authz.tuples t
          ON t.namespace = p_namespace
          AND t.subject_type = um.group_type
          AND t.subject_id = um.group_id
          AND t.relation = 'member'
          AND (t.expires_at IS NULL OR t.expires_at > now())
        WHERE um.depth < authz.max_group_depth()
    )
    SELECT group_type, group_id, membership_relation FROM user_memberships;
$$ LANGUAGE sql STABLE PARALLEL SAFE SET search_path = authz, pg_temp;


-- Compute minimum expiration from two timestamps
--
-- Used when combining expirations in permission chains. If a user's group
-- membership expires in 7 days and the group's permission expires in 30 days,
-- the effective permission expires in 7 days.
--
-- NULL means "never expires" and is treated as infinity.
CREATE OR REPLACE FUNCTION authz.min_expiration(a timestamptz, b timestamptz)
RETURNS timestamptz AS $$
    SELECT CASE
        WHEN a IS NULL THEN b
        WHEN b IS NULL THEN a
        ELSE LEAST(a, b)
    END;
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;
