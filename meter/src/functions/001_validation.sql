-- @group Internal

-- @function meter._validate_namespace
-- @brief Validate namespace format
-- @param p_value Namespace to validate
CREATE FUNCTION meter._validate_namespace(p_value text)
RETURNS void AS $$
BEGIN
    IF p_value IS NULL OR trim(p_value) = '' THEN
        RAISE EXCEPTION 'namespace cannot be null or empty'
            USING ERRCODE = 'null_value_not_allowed';
    END IF;
    IF length(p_value) > 256 THEN
        RAISE EXCEPTION 'namespace exceeds 256 characters'
            USING ERRCODE = 'string_data_right_truncation';
    END IF;
    IF p_value !~ '^[a-z0-9][a-z0-9_-]*$' THEN
        RAISE EXCEPTION 'namespace must be lowercase alphanumeric with underscores/hyphens'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE;


-- @function meter._validate_event_type
-- @brief Validate event_type format
-- @param p_value Event type to validate
CREATE FUNCTION meter._validate_event_type(p_value text)
RETURNS void AS $$
BEGIN
    IF p_value IS NULL OR trim(p_value) = '' THEN
        RAISE EXCEPTION 'event_type cannot be null or empty'
            USING ERRCODE = 'null_value_not_allowed';
    END IF;
    IF length(p_value) > 256 THEN
        RAISE EXCEPTION 'event_type exceeds 256 characters'
            USING ERRCODE = 'string_data_right_truncation';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE;


-- @function meter._validate_unit
-- @brief Validate unit format
-- @param p_value Unit to validate
CREATE FUNCTION meter._validate_unit(p_value text)
RETURNS void AS $$
BEGIN
    IF p_value IS NULL OR trim(p_value) = '' THEN
        RAISE EXCEPTION 'unit cannot be null or empty'
            USING ERRCODE = 'null_value_not_allowed';
    END IF;
    IF length(p_value) > 64 THEN
        RAISE EXCEPTION 'unit exceeds 64 characters'
            USING ERRCODE = 'string_data_right_truncation';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE;


-- @function meter._validate_positive
-- @brief Validate that a numeric value is positive
-- @param p_value Value to validate
-- @param p_name Name of the parameter (for error message)
CREATE FUNCTION meter._validate_positive(p_value numeric, p_name text)
RETURNS void AS $$
BEGIN
    IF p_value IS NULL OR p_value <= 0 THEN
        RAISE EXCEPTION '% must be positive', p_name
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE;
