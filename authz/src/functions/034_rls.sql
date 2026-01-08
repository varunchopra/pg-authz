-- @group Multi-tenancy

-- @function authz.set_tenant
-- @brief Set the tenant context for Row-Level Security (session-level)
-- @param p_tenant_id Tenant/organization ID. All queries will be filtered to this tenant.
-- @example -- At start of request, set tenant from JWT or session
-- @example SELECT authz.set_tenant('acme-corp');
-- @example -- All queries now scoped to acme-corp
CREATE OR REPLACE FUNCTION authz.set_tenant (p_tenant_id text)
    RETURNS VOID
    AS $$
BEGIN
    PERFORM authz._validate_namespace(p_tenant_id);
    PERFORM set_config('authz.tenant_id', p_tenant_id, FALSE);
END;
$$
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = authz, pg_temp;

-- @function authz.clear_tenant
-- @brief Clear tenant context. Queries return no rows (fail-closed for safety).
-- @example SELECT authz.clear_tenant();
CREATE OR REPLACE FUNCTION authz.clear_tenant()
    RETURNS VOID
    AS $$
BEGIN
    PERFORM set_config('authz.tenant_id', '', FALSE);
END;
$$
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = authz, pg_temp;
