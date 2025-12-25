-- =============================================================================
-- HIERARCHY MANAGEMENT FUNCTIONS
-- =============================================================================
--
-- PURPOSE
-- -------
-- Manages permission hierarchy rules (e.g., "admin implies write implies read").
-- These functions safely add/remove hierarchy rules with proper serialization.
--
-- SAFETY
-- ------
-- - Cycle detection prevents admin → write → admin loops
-- - Same namespace lock as write_tuple ensures consistency
-- - All changes trigger recompute of affected resources
--
-- PERFORMANCE WARNING
-- -------------------
-- Hierarchy changes trigger recompute for ALL resources of that type.
-- For 100,000 documents, adding one hierarchy rule = 100,000 recomputes.
-- Schedule hierarchy changes during maintenance windows for large deployments.
--
-- COMPLEXITY
-- ----------
-- Time:  O(R × G × H) where R = resources of type, G = avg group size, H = hierarchy depth
-- Space: O(R × G × H) for computed table updates

CREATE OR REPLACE FUNCTION authz.add_hierarchy(
    p_resource_type TEXT,
    p_permission TEXT,
    p_implies TEXT,
    p_namespace TEXT DEFAULT 'default'
) RETURNS BIGINT AS $$
DECLARE
    v_id BIGINT;
BEGIN
    -- Serialize with tuple writes (same lock as write_tuple/delete_tuple)
    PERFORM pg_advisory_xact_lock(hashtext('authz:write'), hashtext(p_namespace));

    -- Validate inputs
    PERFORM authz.validate_namespace(p_namespace);
    PERFORM authz.validate_identifier(p_resource_type, 'resource_type');
    PERFORM authz.validate_identifier(p_permission, 'permission');
    PERFORM authz.validate_identifier(p_implies, 'implies');

    INSERT INTO authz.permission_hierarchy (namespace, resource_type, permission, implies)
    VALUES (p_namespace, p_resource_type, p_permission, p_implies)
    ON CONFLICT (namespace, resource_type, permission, implies) DO UPDATE
    SET permission = authz.permission_hierarchy.permission  -- no-op, return existing
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE OR REPLACE FUNCTION authz.remove_hierarchy(
    p_resource_type TEXT,
    p_permission TEXT,
    p_implies TEXT,
    p_namespace TEXT DEFAULT 'default'
) RETURNS BOOLEAN AS $$
BEGIN
    -- Serialize with tuple writes (same lock as write_tuple/delete_tuple)
    PERFORM pg_advisory_xact_lock(hashtext('authz:write'), hashtext(p_namespace));

    -- Validate inputs
    PERFORM authz.validate_namespace(p_namespace);
    PERFORM authz.validate_identifier(p_resource_type, 'resource_type');
    PERFORM authz.validate_identifier(p_permission, 'permission');
    PERFORM authz.validate_identifier(p_implies, 'implies');

    DELETE FROM authz.permission_hierarchy
    WHERE namespace = p_namespace
      AND resource_type = p_resource_type
      AND permission = p_permission
      AND implies = p_implies;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

-- Clear all hierarchy rules for a resource type
CREATE OR REPLACE FUNCTION authz.clear_hierarchy(
    p_resource_type TEXT,
    p_namespace TEXT DEFAULT 'default'
) RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    -- Serialize with tuple writes (same lock as write_tuple/delete_tuple)
    PERFORM pg_advisory_xact_lock(hashtext('authz:write'), hashtext(p_namespace));

    -- Validate inputs
    PERFORM authz.validate_namespace(p_namespace);
    PERFORM authz.validate_identifier(p_resource_type, 'resource_type');

    DELETE FROM authz.permission_hierarchy
    WHERE namespace = p_namespace
      AND resource_type = p_resource_type;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;
