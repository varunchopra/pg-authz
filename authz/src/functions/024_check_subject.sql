-- @group Permission Checks

-- =============================================================================
-- SUBJECT-BASED PERMISSION CHECK
-- =============================================================================
-- Like check() but for any subject type (api_key, service, bot, etc.)
-- Note: _expand_subject_memberships is in 010_helpers.sql

-- @function authz._get_subject_permissions
-- @brief Get all effective permissions for a subject on a resource
-- @param p_subject_type The subject type (e.g., 'api_key', 'service')
-- @param p_subject_id The subject ID
-- @param p_resource_type The resource type
-- @param p_resource_id The resource ID
-- @param p_namespace Namespace (default: 'default')
-- @returns Table of permissions the subject has
-- Like _get_user_permissions but works for any subject type.
CREATE OR REPLACE FUNCTION authz._get_subject_permissions(
    p_subject_type text,
    p_subject_id text,
    p_resource_type text,
    p_resource_id text,
    p_namespace text DEFAULT 'default'
)
RETURNS TABLE(permission text)
AS $$
    WITH RECURSIVE
    -- Phase 1: Find all groups/entities the subject belongs to (including nested)
    subject_memberships AS (
        SELECT * FROM authz._expand_subject_memberships(p_subject_type, p_subject_id, p_namespace)
    ),

    -- Phase 2: Find resource and all ancestor resources (via parent relations)
    resource_chain AS (
        SELECT * FROM authz._expand_resource_ancestors(p_resource_type, p_resource_id, p_namespace)
    ),

    -- Phase 3: Find permissions granted on the resource or any ancestor
    granted_permissions AS (
        -- Direct grants to subject on resource or ancestor
        SELECT t.relation AS perm
        FROM authz.tuples t
        JOIN resource_chain rc
          ON t.resource_type = rc.resource_type
          AND t.resource_id = rc.resource_id
        WHERE t.namespace = p_namespace
          AND t.subject_type = p_subject_type
          AND t.subject_id = p_subject_id
          AND (t.expires_at IS NULL OR t.expires_at > now())

        UNION

        -- Grants via groups (including nested) on resource or ancestor
        SELECT t.relation AS perm
        FROM authz.tuples t
        JOIN resource_chain rc
          ON t.resource_type = rc.resource_type
          AND t.resource_id = rc.resource_id
        JOIN subject_memberships sm
          ON t.subject_type = sm.group_type
          AND t.subject_id = sm.group_id
          AND (t.subject_relation IS NULL OR t.subject_relation = sm.membership_relation)
        WHERE t.namespace = p_namespace
          AND (t.expires_at IS NULL OR t.expires_at > now())
    ),

    -- Phase 4: Expand via permission hierarchy
    -- Check BOTH global namespace (shared app-wide rules) AND tenant namespace (org overrides).
    -- This allows app developers to define defaults while letting customers customize
    -- permission models for their specific org structure.
    all_permissions AS (
        SELECT perm FROM granted_permissions

        UNION

        SELECT h.implies
        FROM all_permissions ap
        JOIN authz.permission_hierarchy h
          ON h.resource_type = p_resource_type
          AND h.permission = ap.perm
          AND h.namespace IN ('global', p_namespace)
    )

    SELECT perm AS permission FROM all_permissions;
$$ LANGUAGE sql STABLE PARALLEL SAFE SECURITY INVOKER SET search_path = authz, pg_temp;


-- @function authz.check_subject
-- @brief Check if any subject type has a permission on a resource
-- @param p_subject_type The subject type (e.g., 'api_key', 'service', 'user')
-- @param p_subject_id The subject ID
-- @param p_permission The permission to verify (e.g., 'read', 'write', 'admin')
-- @param p_resource_type The type of resource (e.g., 'repo', 'doc')
-- @param p_resource_id The resource identifier
-- @returns True if the subject has the permission
-- @example SELECT authz.check_subject('api_key', 'key-123', 'read', 'repo', 'api');
-- @example SELECT authz.check_subject('service', 'billing', 'write', 'customer', 'cust-1');
CREATE OR REPLACE FUNCTION authz.check_subject(
    p_subject_type text,
    p_subject_id text,
    p_permission text,
    p_resource_type text,
    p_resource_id text,
    p_namespace text DEFAULT 'default'
) RETURNS boolean AS $$
BEGIN
    PERFORM authz._warn_namespace_mismatch(p_namespace);
    RETURN EXISTS (
        SELECT 1 FROM authz._get_subject_permissions(
            p_subject_type, p_subject_id, p_resource_type, p_resource_id, p_namespace
        )
        WHERE permission = p_permission
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SECURITY INVOKER SET search_path = authz, pg_temp;


-- @function authz.check_subject_any
-- @brief Check if a subject has any of the specified permissions
-- @param p_subject_type The subject type
-- @param p_subject_id The subject ID
-- @param p_permissions Array of permissions (subject needs at least one)
-- @param p_resource_type The type of resource
-- @param p_resource_id The resource identifier
-- @returns True if the subject has at least one of the permissions
-- @example SELECT authz.check_subject_any('api_key', 'key-123', ARRAY['read', 'write'], 'repo', 'api');
CREATE OR REPLACE FUNCTION authz.check_subject_any(
    p_subject_type text,
    p_subject_id text,
    p_permissions text[],
    p_resource_type text,
    p_resource_id text,
    p_namespace text DEFAULT 'default'
) RETURNS boolean AS $$
BEGIN
    PERFORM authz._warn_namespace_mismatch(p_namespace);
    RETURN EXISTS (
        SELECT 1 FROM authz._get_subject_permissions(
            p_subject_type, p_subject_id, p_resource_type, p_resource_id, p_namespace
        )
        WHERE permission = ANY(p_permissions)
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SECURITY INVOKER SET search_path = authz, pg_temp;


-- @function authz.check_subject_all
-- @brief Check if a subject has all of the specified permissions
-- @param p_subject_type The subject type
-- @param p_subject_id The subject ID
-- @param p_permissions Array of permissions (subject needs all of them)
-- @param p_resource_type The type of resource
-- @param p_resource_id The resource identifier
-- @returns True if the subject has all of the permissions
-- @example SELECT authz.check_subject_all('api_key', 'key-123', ARRAY['read', 'write'], 'repo', 'api');
CREATE OR REPLACE FUNCTION authz.check_subject_all(
    p_subject_type text,
    p_subject_id text,
    p_permissions text[],
    p_resource_type text,
    p_resource_id text,
    p_namespace text DEFAULT 'default'
) RETURNS boolean AS $$
BEGIN
    PERFORM authz._warn_namespace_mismatch(p_namespace);
    RETURN COALESCE(array_length(p_permissions, 1), 0) = 0
        OR (
            SELECT COUNT(DISTINCT permission)
            FROM authz._get_subject_permissions(
                p_subject_type, p_subject_id, p_resource_type, p_resource_id, p_namespace
            )
            WHERE permission = ANY(p_permissions)
        ) = array_length(p_permissions, 1);
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SECURITY INVOKER SET search_path = authz, pg_temp;
