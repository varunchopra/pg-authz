-- =============================================================================
-- LIST RESOURCES
-- =============================================================================
-- Returns resources the user can access with the given permission.
-- Supports nested teams and permission hierarchy.
CREATE OR REPLACE FUNCTION authz.list_resources (p_user_id text, p_resource_type text, p_permission text, p_namespace text DEFAULT 'default', p_limit int DEFAULT 100, p_cursor text DEFAULT NULL)
    RETURNS TABLE (
        resource_id text
    )
    AS $$
    WITH RECURSIVE
    -- Find all groups/entities user belongs to (including nested)
    -- Uses reusable helper function to avoid code duplication
    user_memberships AS (
        SELECT * FROM authz._expand_user_memberships(p_user_id, p_namespace)
    ),
-- Find permissions that imply the requested permission (reverse hierarchy)
implied_by AS (
    SELECT
        p_permission AS permission
    UNION
    SELECT
        h.permission
    FROM
        implied_by ib
        JOIN authz.permission_hierarchy h ON h.namespace = p_namespace
            AND h.resource_type = p_resource_type
            AND h.implies = ib.permission
),
-- Find all accessible resources
accessible_resources AS (
    -- Direct grants to user
    SELECT DISTINCT
        t.resource_id
    FROM
        authz.tuples t
    JOIN implied_by ib ON t.relation = ib.permission
    WHERE
        t.namespace = p_namespace
        AND t.resource_type = p_resource_type
        AND t.subject_type = 'user'
        AND t.subject_id = p_user_id
        AND (t.expires_at IS NULL
            OR t.expires_at > now())
    UNION
    -- Grants via groups
    SELECT DISTINCT
        t.resource_id
    FROM
        authz.tuples t
        JOIN implied_by ib ON t.relation = ib.permission
        JOIN user_memberships um ON t.subject_type = um.group_type
            AND t.subject_id = um.group_id
            AND (t.subject_relation IS NULL
                OR t.subject_relation = um.membership_relation)
    WHERE
        t.namespace = p_namespace
        AND t.resource_type = p_resource_type
        AND (t.expires_at IS NULL
            OR t.expires_at > now()))
SELECT
    ar.resource_id
FROM
    accessible_resources ar
WHERE (p_cursor IS NULL
    OR ar.resource_id > p_cursor)
ORDER BY
    ar.resource_id
LIMIT p_limit;
$$
LANGUAGE sql
STABLE PARALLEL SAFE SET search_path = authz, pg_temp;

-- =============================================================================
-- LIST USERS
-- =============================================================================
-- Returns users who can access the resource with the given permission.
-- Expands nested teams to find all member users.
CREATE OR REPLACE FUNCTION authz.list_users (p_resource_type text, p_resource_id text, p_permission text, p_namespace text DEFAULT 'default', p_limit int DEFAULT 100, p_cursor text DEFAULT NULL)
    RETURNS TABLE (
        user_id text
    )
    AS $$
    WITH RECURSIVE
    -- Find permissions that imply the requested permission
    implied_by AS (
        SELECT
            p_permission AS permission
        UNION
        SELECT
            h.permission
        FROM
            implied_by ib
            JOIN authz.permission_hierarchy h ON h.namespace = p_namespace
                AND h.resource_type = p_resource_type
                AND h.implies = ib.permission
),
-- Expand from grantees down to users
-- Start with subjects that have grants on the resource, then recursively
-- expand groups to find all member users
expanded_subjects AS (
    -- Direct grantees on the resource
    SELECT
        t.subject_type,
        t.subject_id,
        t.subject_relation,
        1 AS depth
    FROM
        authz.tuples t
    JOIN implied_by ib ON t.relation = ib.permission
    WHERE
        t.namespace = p_namespace
        AND t.resource_type = p_resource_type
        AND t.resource_id = p_resource_id
        AND (t.expires_at IS NULL
            OR t.expires_at > now())
    UNION
    -- Recursively find members of groups
    SELECT
        t.subject_type,
        t.subject_id,
        t.relation AS subject_relation,
        es.depth + 1
    FROM
        expanded_subjects es
        JOIN authz.tuples t ON t.namespace = p_namespace
            AND t.resource_type = es.subject_type
            AND t.resource_id = es.subject_id
            AND t.relation = COALESCE(es.subject_relation, 'member')
            AND (t.expires_at IS NULL
                OR t.expires_at > now())
    WHERE
        es.subject_type != 'user'
        AND es.depth < authz.max_group_depth()
)
SELECT DISTINCT
    es.subject_id AS user_id
FROM
    expanded_subjects es
WHERE
    es.subject_type = 'user'
    AND (p_cursor IS NULL
        OR es.subject_id > p_cursor)
ORDER BY
    es.subject_id
LIMIT p_limit;
$$
LANGUAGE sql
STABLE PARALLEL SAFE SET search_path = authz, pg_temp;

-- =============================================================================
-- FILTER AUTHORIZED (batch check)
-- =============================================================================
-- Given a list of resource IDs, returns only those the user can access.
CREATE OR REPLACE FUNCTION authz.filter_authorized (p_user_id text, p_resource_type text, p_permission text, p_resource_ids text[], p_namespace text DEFAULT 'default')
    RETURNS text[]
    AS $$
    -- Find all groups/entities user belongs to (including nested)
    -- Uses reusable helper function to avoid code duplication
    WITH RECURSIVE user_memberships AS (
        SELECT * FROM authz._expand_user_memberships(p_user_id, p_namespace)
    ),
implied_by AS (
    SELECT
        p_permission AS permission
    UNION
    SELECT
        h.permission
    FROM
        implied_by ib
        JOIN authz.permission_hierarchy h ON h.namespace = p_namespace
            AND h.resource_type = p_resource_type
            AND h.implies = ib.permission
),
accessible AS (
    -- Direct grants
    SELECT DISTINCT
        t.resource_id
    FROM
        authz.tuples t
    JOIN implied_by ib ON t.relation = ib.permission
    WHERE
        t.namespace = p_namespace
        AND t.resource_type = p_resource_type
        AND t.resource_id = ANY (p_resource_ids)
        AND t.subject_type = 'user'
        AND t.subject_id = p_user_id
        AND (t.expires_at IS NULL
            OR t.expires_at > now())
    UNION
    -- Group grants
    SELECT DISTINCT
        t.resource_id
    FROM
        authz.tuples t
        JOIN implied_by ib ON t.relation = ib.permission
        JOIN user_memberships um ON t.subject_type = um.group_type
            AND t.subject_id = um.group_id
            AND (t.subject_relation IS NULL
                OR t.subject_relation = um.membership_relation)
    WHERE
        t.namespace = p_namespace
        AND t.resource_type = p_resource_type
        AND t.resource_id = ANY (p_resource_ids)
        AND (t.expires_at IS NULL
            OR t.expires_at > now()))
SELECT
    ARRAY (
        SELECT
            resource_id
        FROM
            accessible
        ORDER BY
            resource_id);
$$
LANGUAGE sql
STABLE PARALLEL SAFE SET search_path = authz, pg_temp;
