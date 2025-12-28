-- @group Internal

-- @function authz._max_group_depth
-- @brief Maximum recursion depth for nested group traversal
-- @returns 50 (prevents infinite loops if cycles exist)
CREATE OR REPLACE FUNCTION authz._max_group_depth()
RETURNS int AS $$
    SELECT 50::int;
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE SECURITY INVOKER;


-- @function authz._max_resource_depth
-- @brief Maximum recursion depth for resource hierarchy traversal
-- @returns 50 (limits how deep parent relations are followed)
CREATE OR REPLACE FUNCTION authz._max_resource_depth()
RETURNS int AS $$
    SELECT 50::int;
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE SECURITY INVOKER;
