-- =============================================================================
-- DELETE TUPLE - Remove a relationship from the authorization graph
-- =============================================================================
--
-- PURPOSE
-- -------
-- Removes a relationship tuple, revoking the associated permission.
-- Triggers automatically recompute affected computed permissions.
--
-- COMPLEXITY
-- ----------
-- Time:  O(G + H) where G = group members affected, H = hierarchy depth
-- Space: O(1) - only removes entries, doesn't add
--
-- IDEMPOTENCY
-- ===========
-- Deleting a non-existent tuple returns FALSE but causes no error.
-- This is safe for retries and declarative "ensure this permission is gone" patterns.
--
-- RETURNS
-- -------
-- TRUE if a tuple was deleted, FALSE if tuple didn't exist.

CREATE OR REPLACE FUNCTION authz.delete_tuple(
    p_resource_type TEXT,
    p_resource_id TEXT,
    p_relation TEXT,
    p_subject_type TEXT,
    p_subject_id TEXT,
    p_subject_relation TEXT DEFAULT NULL,
    p_namespace TEXT DEFAULT 'default'
) RETURNS BOOLEAN AS $$
BEGIN
    -- Serialize ALL writes within this namespace (same lock as write_tuple)
    PERFORM pg_advisory_xact_lock(hashtext('authz:write'), hashtext(p_namespace));

    -- Validate all inputs (consistent with write_tuple)
    PERFORM authz.validate_tuple_fields(
        p_namespace, p_resource_type, p_resource_id,
        p_relation, p_subject_type, p_subject_id, p_subject_relation
    );

    DELETE FROM authz.tuples
    WHERE namespace = p_namespace
      AND resource_type = p_resource_type
      AND resource_id = p_resource_id
      AND relation = p_relation
      AND subject_type = p_subject_type
      AND subject_id = p_subject_id
      AND COALESCE(subject_relation, '') = COALESCE(p_subject_relation, '');

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

-- Convenience alias
CREATE OR REPLACE FUNCTION authz.delete(
    p_resource_type TEXT,
    p_resource_id TEXT,
    p_relation TEXT,
    p_subject_type TEXT,
    p_subject_id TEXT,
    p_namespace TEXT DEFAULT 'default'
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN authz.delete_tuple(p_resource_type, p_resource_id, p_relation, p_subject_type, p_subject_id, NULL, p_namespace);
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;
