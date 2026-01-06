-- @group MFA

-- @function authn.add_mfa
-- @brief Add an MFA method (TOTP, WebAuthn, or recovery codes)
-- @param p_mfa_type One of: 'totp', 'webauthn', 'recovery_codes'
-- @param p_secret The secret to store (TOTP seed, WebAuthn public key, etc.)
-- @param p_name User-friendly name like "My iPhone" or "Backup codes"
-- @returns MFA method ID
-- @example SELECT authn.add_mfa(user_id, 'totp', 'JBSWY3DPEHPK3PXP', 'Authenticator');
CREATE OR REPLACE FUNCTION authn.add_mfa(
    p_user_id uuid,
    p_mfa_type text,
    p_secret text,
    p_name text DEFAULT NULL,
    p_namespace text DEFAULT 'default'
)
RETURNS uuid
AS $$
DECLARE
    v_mfa_id uuid;
BEGIN
    PERFORM authn._validate_mfa_type(p_mfa_type);
    PERFORM authn._validate_secret(p_secret);
    PERFORM authn._validate_namespace(p_namespace);

    INSERT INTO authn.mfa_secrets (
        namespace, user_id, mfa_type, secret, name
    ) VALUES (
        p_namespace, p_user_id, p_mfa_type, p_secret, p_name
    )
    RETURNING id INTO v_mfa_id;

    -- Audit log (never log secret!)
    PERFORM authn._log_event(
        'mfa_added', p_namespace, 'mfa', v_mfa_id::text,
        NULL,
        jsonb_build_object('user_id', p_user_id, 'mfa_type', p_mfa_type, 'name', p_name)
    );

    RETURN v_mfa_id;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.get_mfa
-- @brief Get MFA secrets for verification (returns raw secrets)
-- @returns mfa_id, secret, name. Use to verify TOTP code or WebAuthn assertion.
-- @example SELECT * FROM authn.get_mfa(user_id, 'totp'); -- Verify code against secret
CREATE OR REPLACE FUNCTION authn.get_mfa(
    p_user_id uuid,
    p_mfa_type text,
    p_namespace text DEFAULT 'default'
)
RETURNS TABLE(
    mfa_id uuid,
    secret text,
    name text
)
AS $$
BEGIN
    PERFORM authn._validate_mfa_type(p_mfa_type);
    PERFORM authn._validate_namespace(p_namespace);
    PERFORM authn._warn_namespace_mismatch(p_namespace);

    RETURN QUERY
    SELECT
        m.id AS mfa_id,
        m.secret,
        m.name
    FROM authn.mfa_secrets m
    WHERE m.user_id = p_user_id
      AND m.mfa_type = p_mfa_type
      AND m.namespace = p_namespace;
END;
$$ LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.list_mfa
-- @brief List user's MFA methods for "manage security" UI (no secrets)
-- @example SELECT * FROM authn.list_mfa(user_id);
CREATE OR REPLACE FUNCTION authn.list_mfa(
    p_user_id uuid,
    p_namespace text DEFAULT 'default'
)
RETURNS TABLE(
    mfa_id uuid,
    mfa_type text,
    name text,
    created_at timestamptz,
    last_used_at timestamptz
)
AS $$
BEGIN
    PERFORM authn._validate_namespace(p_namespace);
    PERFORM authn._warn_namespace_mismatch(p_namespace);

    RETURN QUERY
    SELECT
        m.id AS mfa_id,
        m.mfa_type,
        m.name,
        m.created_at,
        m.last_used_at
    FROM authn.mfa_secrets m
    WHERE m.user_id = p_user_id
      AND m.namespace = p_namespace
    ORDER BY m.created_at;
END;
$$ LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.remove_mfa
-- @brief Remove an MFA method
-- @example SELECT authn.remove_mfa(mfa_id);
CREATE OR REPLACE FUNCTION authn.remove_mfa(
    p_mfa_id uuid,
    p_namespace text DEFAULT 'default'
)
RETURNS boolean
AS $$
DECLARE
    v_user_id uuid;
    v_mfa_type text;
    v_name text;
    v_count int;
BEGIN
    PERFORM authn._validate_namespace(p_namespace);

    -- Get info for audit before deletion
    SELECT user_id, mfa_type, name
    INTO v_user_id, v_mfa_type, v_name
    FROM authn.mfa_secrets
    WHERE id = p_mfa_id AND namespace = p_namespace;

    IF v_user_id IS NULL THEN
        RETURN false;
    END IF;

    DELETE FROM authn.mfa_secrets
    WHERE id = p_mfa_id
      AND namespace = p_namespace;

    GET DIAGNOSTICS v_count = ROW_COUNT;

    IF v_count > 0 THEN
        -- Audit log
        PERFORM authn._log_event(
            'mfa_removed', p_namespace, 'mfa', p_mfa_id::text,
            jsonb_build_object('user_id', v_user_id, 'mfa_type', v_mfa_type, 'name', v_name)
        );
    END IF;

    RETURN v_count > 0;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.record_mfa_use
-- @brief Record successful MFA verification (updates last_used_at)
-- @example -- After verifying TOTP code
-- @example SELECT authn.record_mfa_use(mfa_id);
CREATE OR REPLACE FUNCTION authn.record_mfa_use(
    p_mfa_id uuid,
    p_namespace text DEFAULT 'default'
)
RETURNS boolean
AS $$
DECLARE
    v_count int;
BEGIN
    PERFORM authn._validate_namespace(p_namespace);

    UPDATE authn.mfa_secrets
    SET last_used_at = now()
    WHERE id = p_mfa_id
      AND namespace = p_namespace;

    GET DIAGNOSTICS v_count = ROW_COUNT;

    IF v_count > 0 THEN
        -- Audit log
        PERFORM authn._log_event(
            'mfa_used', p_namespace, 'mfa', p_mfa_id::text
        );
    END IF;

    RETURN v_count > 0;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = authn, pg_temp;

-- @function authn.has_mfa
-- @brief Check if user has any MFA method configured
-- @example IF authn.has_mfa(user_id) THEN prompt_for_mfa(); END IF;
CREATE OR REPLACE FUNCTION authn.has_mfa(
    p_user_id uuid,
    p_namespace text DEFAULT 'default'
)
RETURNS boolean
AS $$
BEGIN
    PERFORM authn._validate_namespace(p_namespace);

    RETURN EXISTS (
        SELECT 1
        FROM authn.mfa_secrets
        WHERE user_id = p_user_id
          AND namespace = p_namespace
    );
END;
$$ LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = authn, pg_temp;

