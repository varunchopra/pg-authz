-- @group Subject Grants

-- @function authz.list_subject_grants
-- @brief List all grants for a subject ("What can this API key access?")
-- @param p_subject_type Subject type (e.g., 'api_key', 'service')
-- @param p_subject_id Subject identifier
-- @param p_namespace Namespace to search in
-- @param p_resource_type Optional filter by resource type
-- @returns All active (non-expired) grants for this subject
-- @example -- Get all grants for an API key
-- @example SELECT * FROM authz.list_subject_grants('api_key', 'key-123', 'default');
-- @example -- Get only note-related grants
-- @example SELECT * FROM authz.list_subject_grants('api_key', 'key-123', 'default', 'note');
CREATE OR REPLACE FUNCTION authz.list_subject_grants(
    p_subject_type text,
    p_subject_id text,
    p_namespace text DEFAULT 'default',
    p_resource_type text DEFAULT NULL
) RETURNS TABLE (
    resource_type text,
    resource_id text,
    relation text,
    subject_relation text,
    expires_at timestamptz
) AS $$
    SELECT t.resource_type, t.resource_id, t.relation,
           t.subject_relation, t.expires_at
    FROM authz.tuples t
    WHERE t.namespace = p_namespace
      AND t.subject_type = p_subject_type
      AND t.subject_id = p_subject_id
      AND (p_resource_type IS NULL OR t.resource_type = p_resource_type)
      AND (t.expires_at IS NULL OR t.expires_at > now())
    ORDER BY t.resource_type, t.resource_id, t.relation;
$$ LANGUAGE sql STABLE PARALLEL SAFE SECURITY INVOKER
   SET search_path = authz, pg_temp;

-- @function authz.revoke_subject_grants
-- @brief Revoke all grants for a subject (cleanup on deletion)
-- @param p_subject_type Subject type (e.g., 'api_key', 'service')
-- @param p_subject_id Subject identifier
-- @param p_namespace Namespace to search in
-- @param p_resource_type Optional filter to only revoke grants on specific resource type
-- @returns Count of grants revoked
-- @example -- Revoke all grants for an API key before deletion
-- @example SELECT authz.revoke_subject_grants('api_key', 'key-123', 'default');
-- @example -- Revoke only note-related grants
-- @example SELECT authz.revoke_subject_grants('api_key', 'key-123', 'default', 'note');
CREATE OR REPLACE FUNCTION authz.revoke_subject_grants(
    p_subject_type text,
    p_subject_id text,
    p_namespace text DEFAULT 'default',
    p_resource_type text DEFAULT NULL
) RETURNS integer AS $$
DECLARE
    v_deleted integer;
BEGIN
    -- Validate inputs
    PERFORM authz._validate_identifier(p_subject_type, 'subject_type');
    PERFORM authz._validate_id(p_subject_id, 'subject_id');
    PERFORM authz._validate_namespace(p_namespace);
    IF p_resource_type IS NOT NULL THEN
        PERFORM authz._validate_identifier(p_resource_type, 'resource_type');
    END IF;

    DELETE FROM authz.tuples
    WHERE namespace = p_namespace
      AND subject_type = p_subject_type
      AND subject_id = p_subject_id
      AND (p_resource_type IS NULL OR resource_type = p_resource_type);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authz, pg_temp;

-- @function authz.revoke_resource_grants
-- @brief Revoke all grants on a resource (cleanup when deleting a resource)
-- @param p_resource_type Resource type (e.g., 'note', 'doc', 'repo')
-- @param p_resource_id Resource identifier
-- @param p_namespace Namespace to search in
-- @param p_relation Optional filter to only revoke specific relation/permission
-- @returns Count of grants revoked
-- @example -- Revoke all grants on a note before deletion
-- @example SELECT authz.revoke_resource_grants('note', 'note-123', 'default');
-- @example -- Revoke only 'view' grants on a note
-- @example SELECT authz.revoke_resource_grants('note', 'note-123', 'default', 'view');
CREATE OR REPLACE FUNCTION authz.revoke_resource_grants(
    p_resource_type text,
    p_resource_id text,
    p_namespace text DEFAULT 'default',
    p_relation text DEFAULT NULL
) RETURNS integer AS $$
DECLARE
    v_deleted integer;
BEGIN
    -- Validate inputs
    PERFORM authz._validate_identifier(p_resource_type, 'resource_type');
    PERFORM authz._validate_id(p_resource_id, 'resource_id');
    PERFORM authz._validate_namespace(p_namespace);
    IF p_relation IS NOT NULL THEN
        PERFORM authz._validate_identifier(p_relation, 'relation');
    END IF;

    DELETE FROM authz.tuples
    WHERE namespace = p_namespace
      AND resource_type = p_resource_type
      AND resource_id = p_resource_id
      AND (p_relation IS NULL OR relation = p_relation);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authz, pg_temp;
