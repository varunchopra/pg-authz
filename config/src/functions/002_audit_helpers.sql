-- @group Internal

-- @function config._log_event
-- @brief Internal helper that inserts audit events with actor context
CREATE OR REPLACE FUNCTION config._log_event(
    p_event_type text,
    p_namespace text,
    p_key text,
    p_version int DEFAULT NULL,
    p_old_value jsonb DEFAULT NULL,
    p_new_value jsonb DEFAULT NULL
)
RETURNS void
AS $$
BEGIN
    INSERT INTO config.audit_events (
        event_type,
        namespace,
        key,
        version,
        actor_id,
        request_id,
        reason,
        on_behalf_of,
        old_value,
        new_value
    ) VALUES (
        p_event_type,
        p_namespace,
        p_key,
        p_version,
        nullif(current_setting('config.actor_id', true), ''),
        nullif(current_setting('config.request_id', true), ''),
        nullif(current_setting('config.reason', true), ''),
        nullif(current_setting('config.on_behalf_of', true), ''),
        p_old_value,
        p_new_value
    );
END;
$$ LANGUAGE plpgsql SECURITY INVOKER SET search_path = config, pg_temp;
