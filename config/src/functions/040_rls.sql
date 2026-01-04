-- @group Multi-tenancy

-- @function config.set_tenant
-- @brief Set the tenant context for Row-Level Security
-- @param p_tenant_id The tenant/namespace ID
-- @example SELECT config.set_tenant('acme-corp');
CREATE OR REPLACE FUNCTION config.set_tenant(p_tenant_id text)
RETURNS void
AS $$
BEGIN
    PERFORM config._validate_namespace(p_tenant_id);
    PERFORM set_config('config.tenant_id', p_tenant_id, true);
END;
$$ LANGUAGE plpgsql SET search_path = config, pg_temp;


-- @function config.clear_tenant
-- @brief Clear tenant context. Queries return no rows (fail-closed for safety).
CREATE OR REPLACE FUNCTION config.clear_tenant()
RETURNS void
AS $$
BEGIN
    PERFORM set_config('config.tenant_id', '', true);
END;
$$ LANGUAGE plpgsql SET search_path = config, pg_temp;
