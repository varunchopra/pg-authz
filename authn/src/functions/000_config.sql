-- @group Internal

-- @function authn._session_duration
-- @brief Returns default session duration
-- @returns Interval (default: 7 days)
-- Override with SET authn.session_duration.
CREATE OR REPLACE FUNCTION authn._session_duration()
RETURNS interval
AS $$
BEGIN
    RETURN COALESCE(
        current_setting('authn.session_duration', true)::interval,
        '7 days'::interval
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SET search_path = authn, pg_temp;


-- @function authn._token_expiry
-- @brief Returns default token expiry for a given token type
-- @param p_token_type Token type (password_reset, email_verify, magic_link)
-- @returns Interval (password_reset: 1 hour, email_verify: 24 hours, magic_link: 15 minutes)
CREATE OR REPLACE FUNCTION authn._token_expiry(p_token_type text)
RETURNS interval
AS $$
BEGIN
    RETURN CASE p_token_type
        WHEN 'password_reset' THEN '1 hour'::interval
        WHEN 'email_verify' THEN '24 hours'::interval
        WHEN 'magic_link' THEN '15 minutes'::interval
        ELSE '1 hour'::interval  -- Fallback for unknown types
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SET search_path = authn, pg_temp;


-- @function authn._lockout_window
-- @brief Returns lockout window duration
-- @returns Interval (default: 15 minutes)
-- Override with SET authn.lockout_window.
CREATE OR REPLACE FUNCTION authn._lockout_window()
RETURNS interval
AS $$
BEGIN
    RETURN COALESCE(
        current_setting('authn.lockout_window', true)::interval,
        '15 minutes'::interval
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SET search_path = authn, pg_temp;


-- @function authn._max_login_attempts
-- @brief Returns max failed attempts before lockout
-- @returns Integer (default: 5)
-- Override with SET authn.max_login_attempts.
CREATE OR REPLACE FUNCTION authn._max_login_attempts()
RETURNS int
AS $$
BEGIN
    RETURN COALESCE(
        current_setting('authn.max_login_attempts', true)::int,
        5
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SET search_path = authn, pg_temp;


-- @function authn._login_attempts_retention
-- @brief Returns how long to keep login attempts
-- @returns Interval (default: 30 days)
-- Override with SET authn.login_attempts_retention.
CREATE OR REPLACE FUNCTION authn._login_attempts_retention()
RETURNS interval
AS $$
BEGIN
    RETURN COALESCE(
        current_setting('authn.login_attempts_retention', true)::interval,
        '30 days'::interval
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SET search_path = authn, pg_temp;
