-- @group API Keys

-- @function authn.create_api_key
-- @brief Create an API key for programmatic access
-- @param p_user_id Owner of the key
-- @param p_key_hash SHA-256 hash of the actual key (caller generates, hashes, stores hash)
-- @param p_name Optional friendly name ("Production", "CI/CD")
-- @param p_expires_in Optional expiration interval (NULL = never expires)
-- @returns API key ID
-- @example SELECT authn.create_api_key(user_id, sha256(key), 'Production', '1 year');
CREATE OR REPLACE FUNCTION authn.create_api_key(
    p_user_id uuid,
    p_key_hash text,
    p_name text DEFAULT NULL,
    p_expires_in interval DEFAULT NULL,
    p_namespace text DEFAULT 'default'
)
RETURNS uuid
AS $$
DECLARE
    v_key_id uuid;
    v_expires_at timestamptz;
BEGIN
    PERFORM authn._validate_hash(p_key_hash, 'key_hash', false);
    PERFORM authn._validate_namespace(p_namespace);

    -- Calculate expiration (NULL means never expires)
    IF p_expires_in IS NOT NULL THEN
        v_expires_at := now() + p_expires_in;
    END IF;

    INSERT INTO authn.api_keys (
        namespace, user_id, key_hash, name, expires_at
    ) VALUES (
        p_namespace, p_user_id, p_key_hash, p_name, v_expires_at
    )
    RETURNING id INTO v_key_id;

    -- Audit log (never log key_hash!)
    PERFORM authn._log_event(
        'api_key_created', p_namespace, 'api_key', v_key_id::text,
        NULL,
        jsonb_build_object('user_id', p_user_id, 'name', p_name, 'expires_at', v_expires_at)
    );

    RETURN v_key_id;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.validate_api_key
-- @brief Validate an API key and get owner info (hot path)
-- @param p_key_hash SHA-256 hash of the key being validated
-- @returns user_id, key_id, name, expires_at if valid; empty if invalid/expired/revoked
-- @note Updates last_used_at on successful validation
-- @example SELECT * FROM authn.validate_api_key(sha256(key_from_header));
CREATE OR REPLACE FUNCTION authn.validate_api_key(
    p_key_hash text,
    p_namespace text DEFAULT 'default'
)
RETURNS TABLE(
    user_id uuid,
    key_id uuid,
    name text,
    expires_at timestamptz
)
AS $$
DECLARE
    v_key_id uuid;
BEGIN
    PERFORM authn._validate_hash(p_key_hash, 'key_hash', false);
    PERFORM authn._validate_namespace(p_namespace);

    -- Find valid key and update last_used_at in one query
    UPDATE authn.api_keys ak
    SET last_used_at = now()
    WHERE ak.key_hash = p_key_hash
      AND ak.namespace = p_namespace
      AND ak.revoked_at IS NULL
      AND (ak.expires_at IS NULL OR ak.expires_at > now())
      AND EXISTS (
          SELECT 1 FROM authn.users u
          WHERE u.id = ak.user_id
            AND u.namespace = ak.namespace
            AND u.disabled_at IS NULL
      )
    RETURNING ak.id INTO v_key_id;

    -- Return key info if found
    IF v_key_id IS NOT NULL THEN
        RETURN QUERY
        SELECT
            ak.user_id,
            ak.id AS key_id,
            ak.name,
            ak.expires_at
        FROM authn.api_keys ak
        WHERE ak.id = v_key_id;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.revoke_api_key
-- @brief Revoke an API key
-- @param p_key_id The key ID to revoke
-- @returns True if key was revoked, false if not found or already revoked
-- @example SELECT authn.revoke_api_key('key-uuid-here');
CREATE OR REPLACE FUNCTION authn.revoke_api_key(
    p_key_id uuid,
    p_namespace text DEFAULT 'default'
)
RETURNS boolean
AS $$
DECLARE
    v_user_id uuid;
    v_name text;
    v_count int;
BEGIN
    PERFORM authn._validate_namespace(p_namespace);

    UPDATE authn.api_keys
    SET revoked_at = now()
    WHERE id = p_key_id
      AND namespace = p_namespace
      AND revoked_at IS NULL
    RETURNING user_id, name INTO v_user_id, v_name;

    GET DIAGNOSTICS v_count = ROW_COUNT;

    IF v_count > 0 THEN
        -- Audit log
        PERFORM authn._log_event(
            'api_key_revoked', p_namespace, 'api_key', p_key_id::text,
            NULL, jsonb_build_object('user_id', v_user_id, 'name', v_name)
        );
    END IF;

    RETURN v_count > 0;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.revoke_all_api_keys
-- @brief Revoke all API keys for a user
-- @param p_user_id The user whose keys to revoke
-- @returns Count of keys revoked
-- @example SELECT authn.revoke_all_api_keys(user_id); -- Security concern, revoke all
CREATE OR REPLACE FUNCTION authn.revoke_all_api_keys(
    p_user_id uuid,
    p_namespace text DEFAULT 'default'
)
RETURNS int
AS $$
DECLARE
    v_count int;
BEGIN
    PERFORM authn._validate_namespace(p_namespace);

    UPDATE authn.api_keys
    SET revoked_at = now()
    WHERE user_id = p_user_id
      AND namespace = p_namespace
      AND revoked_at IS NULL;

    GET DIAGNOSTICS v_count = ROW_COUNT;

    IF v_count > 0 THEN
        -- Audit log
        PERFORM authn._log_event(
            'api_keys_revoked_all', p_namespace, 'user', p_user_id::text,
            NULL, jsonb_build_object('keys_revoked', v_count)
        );
    END IF;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.list_api_keys
-- @brief List API keys for a user (for management UI)
-- @param p_user_id The user whose keys to list
-- @returns Active keys with metadata (no key_hash exposed)
-- @example SELECT * FROM authn.list_api_keys(user_id);
CREATE OR REPLACE FUNCTION authn.list_api_keys(
    p_user_id uuid,
    p_namespace text DEFAULT 'default'
)
RETURNS TABLE(
    key_id uuid,
    name text,
    created_at timestamptz,
    expires_at timestamptz,
    last_used_at timestamptz
)
AS $$
BEGIN
    PERFORM authn._validate_namespace(p_namespace);
    PERFORM authn._warn_namespace_mismatch(p_namespace);

    RETURN QUERY
    SELECT
        ak.id AS key_id,
        ak.name,
        ak.created_at,
        ak.expires_at,
        ak.last_used_at
    FROM authn.api_keys ak
    WHERE ak.user_id = p_user_id
      AND ak.namespace = p_namespace
      AND ak.revoked_at IS NULL
      AND (ak.expires_at IS NULL OR ak.expires_at > now())
    ORDER BY ak.created_at DESC;
END;
$$ LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = authn, pg_temp;
