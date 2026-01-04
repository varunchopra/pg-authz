-- @group Internal

-- @function config._validate_key
-- @brief Validates config key format
-- @param p_key The key to validate
-- Allows paths like 'prompts/support-bot', 'flags/checkout-v2', 'secrets/OPENAI_API_KEY'
CREATE OR REPLACE FUNCTION config._validate_key(p_key text)
RETURNS void
AS $$
BEGIN
    IF p_key IS NULL THEN
        RAISE EXCEPTION 'key cannot be null'
            USING ERRCODE = 'null_value_not_allowed';
    END IF;

    IF trim(p_key) = '' THEN
        RAISE EXCEPTION 'key cannot be empty'
            USING ERRCODE = 'string_data_length_mismatch';
    END IF;

    IF length(p_key) > 1024 THEN
        RAISE EXCEPTION 'key exceeds maximum length of 1024 characters'
            USING ERRCODE = 'string_data_right_truncation';
    END IF;

    -- Allow alphanumeric, underscores, hyphens, forward slashes, dots
    -- Must start with letter or number
    IF p_key !~ '^[a-zA-Z0-9][a-zA-Z0-9_/.-]*$' THEN
        RAISE EXCEPTION 'key must start with alphanumeric and contain only alphanumerics, underscores, hyphens, forward slashes, and dots (got: %)', p_key
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- Reject double slashes, leading/trailing slashes
    IF p_key ~ '//' OR p_key ~ '^/' OR p_key ~ '/$' THEN
        RAISE EXCEPTION 'key cannot have double slashes or leading/trailing slashes (got: %)', p_key
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SECURITY INVOKER SET search_path = config, pg_temp;


-- @function config._validate_namespace
-- @brief Validates namespace format
CREATE OR REPLACE FUNCTION config._validate_namespace(p_value text)
RETURNS void
AS $$
BEGIN
    IF p_value IS NULL THEN
        RAISE EXCEPTION 'namespace cannot be null'
            USING ERRCODE = 'null_value_not_allowed';
    END IF;

    IF trim(p_value) = '' THEN
        RAISE EXCEPTION 'namespace cannot be empty'
            USING ERRCODE = 'string_data_length_mismatch';
    END IF;

    IF length(p_value) > 1024 THEN
        RAISE EXCEPTION 'namespace exceeds maximum length of 1024 characters'
            USING ERRCODE = 'string_data_right_truncation';
    END IF;

    IF p_value !~ '^[a-z0-9][a-z0-9_-]*$' THEN
        RAISE EXCEPTION 'namespace must be lowercase alphanumeric with underscores/hyphens (got: %)', p_value
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SECURITY INVOKER SET search_path = config, pg_temp;


-- @function config._warn_namespace_mismatch
-- @brief Warns if namespace doesn't match RLS tenant context
CREATE OR REPLACE FUNCTION config._warn_namespace_mismatch(p_namespace text)
RETURNS void
AS $$
DECLARE
    v_tenant_id text;
BEGIN
    v_tenant_id := current_setting('config.tenant_id', true);
    IF v_tenant_id IS NOT NULL AND v_tenant_id != '' AND p_namespace != v_tenant_id THEN
        RAISE WARNING 'Querying namespace "%" but RLS tenant context is "%". Results will be empty due to row-level security.',
            p_namespace, v_tenant_id;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SECURITY INVOKER SET search_path = config, pg_temp;
