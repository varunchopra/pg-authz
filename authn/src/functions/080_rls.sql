-- @group Multi-tenancy

-- @function authn.set_tenant
-- @brief Set the tenant context for Row-Level Security
-- @param p_tenant_id Tenant/organization ID. All queries will be filtered to this tenant.
-- @example -- At start of request, set tenant from JWT or session
-- @example SELECT authn.set_tenant('acme-corp');
CREATE OR REPLACE FUNCTION authn.set_tenant(
    p_tenant_id text
)
RETURNS void
AS $$
BEGIN
    PERFORM authn._validate_namespace(p_tenant_id);
    PERFORM set_config('authn.tenant_id', p_tenant_id, true);
END;
$$ LANGUAGE plpgsql SET search_path = authn, pg_temp;

-- @function authn.clear_tenant
-- @brief Clear tenant context. Queries return no rows (fail-closed for safety).
-- @example SELECT authn.clear_tenant();
CREATE OR REPLACE FUNCTION authn.clear_tenant()
RETURNS void
AS $$
BEGIN
    PERFORM set_config('authn.tenant_id', '', true);
END;
$$ LANGUAGE plpgsql SET search_path = authn, pg_temp;

