-- =============================================================================
-- EXPLAIN PERMISSION - Trace how a user got a permission
-- =============================================================================
--
-- WHY THIS FUNCTION EXISTS
-- ========================
-- The computed table stores WHAT permissions a user has, but not WHY.
-- This is intentional - a permission can come from multiple sources:
--   1. Direct grant (tuple: user has permission on resource)
--   2. Group membership (tuple: user is member of group that has permission)
--   3. Permission hierarchy (config: admin implies read)
--
-- Storing one "source" in the computed table would be misleading. Instead,
-- this function traces the permission graph on-demand when you need to debug.
--
-- ALGORITHM: BACKWARD CHAINING
-- ============================
-- We start from the question "does user X have permission Y on resource Z?"
-- and work backwards through all possible paths that could grant it:
--
--   1. Check direct: Is there a tuple (resource, relation=permission, user)?
--   2. Check groups: Is there a tuple (resource, relation=permission, group)
--      where user is a member of that group?
--   3. Check hierarchy: Is there a higher permission that implies this one?
--      If so, recursively explain how they got the higher permission.
--
-- EXAMPLE WALKTHROUGH
-- ===================
-- Question: How does alice have 'read' on repo:api?
--
-- Given tuples:
--   (repo, api, admin, team, engineering)
--   (team, engineering, member, user, alice)
--
-- Given hierarchy:
--   (repo, admin, read) -- admin implies read
--
-- Trace:
--   1. Direct 'read' on repo:api? No tuple found.
--   2. Group 'read' on repo:api? No tuple found.
--   3. Hierarchy: what implies 'read'? 'admin' does.
--      Recursively: How does alice have 'admin' on repo:api?
--        1. Direct 'admin'? No.
--        2. Group 'admin'? Yes! team:engineering has admin, alice is member.
--
-- Result:
--   path: "team:engineering#member -> repo:api#admin -> (hierarchy) -> read"
--
-- PERFORMANCE NOTE
-- ================
-- This function does graph traversal at query time. It's designed for
-- debugging and auditing, NOT for hot paths. For permission checks,
-- always use authz.check() which does O(1) lookups on pre-computed data.

-- Return type for explain results
-- Use DO block to avoid breaking existing functions on re-install
DO $$ BEGIN
    CREATE TYPE authz.permission_path AS (
        path_type TEXT,           -- 'direct', 'group', 'hierarchy'
        via_relation TEXT,        -- The relation that granted access (e.g., 'admin')
        via_subject_type TEXT,    -- For group paths: the group type (e.g., 'team')
        via_subject_id TEXT,      -- For group paths: the group id (e.g., 'engineering')
        via_membership TEXT,      -- For group paths: how user relates to group (e.g., 'member')
        implies_chain TEXT[]      -- For hierarchy: chain of implications (e.g., ['admin', 'write', 'read'])
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Explain how a user has (or doesn't have) a permission
CREATE OR REPLACE FUNCTION authz.explain(
    p_user_id TEXT,
    p_permission TEXT,
    p_resource_type TEXT,
    p_resource_id TEXT,
    p_namespace TEXT DEFAULT 'default',
    p_max_depth INT DEFAULT 20
) RETURNS SETOF authz.permission_path AS $$
DECLARE
    v_path authz.permission_path;
    v_higher_permission TEXT;
    v_chain TEXT[];
    v_higher_path authz.permission_path;
BEGIN
    -- Depth limit to prevent runaway recursion on malformed data
    IF p_max_depth <= 0 THEN
        RAISE WARNING 'explain() reached maximum recursion depth for permission % on %:%',
            p_permission, p_resource_type, p_resource_id;
        RETURN;
    END IF;
    -- ==========================================================================
    -- PATH 1: DIRECT PERMISSION
    -- ==========================================================================
    -- Check if there's a tuple directly granting this permission to the user.
    -- This is the simplest case: (resource, permission, user)

    FOR v_path IN
        SELECT
            'direct'::TEXT,
            t.relation,
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT,
            NULL::TEXT[]
        FROM authz.tuples t
        WHERE t.namespace = p_namespace
          AND t.resource_type = p_resource_type
          AND t.resource_id = p_resource_id
          AND t.relation = p_permission
          AND t.subject_type = 'user'
          AND t.subject_id = p_user_id
          AND t.subject_relation IS NULL
    LOOP
        RETURN NEXT v_path;
    END LOOP;

    -- ==========================================================================
    -- PATH 2: GROUP MEMBERSHIP
    -- ==========================================================================
    -- Check if the user is a member of a group that has this permission.
    -- Two-hop query:
    --   1. Find tuples granting permission to non-user subjects (groups)
    --   2. Check if user is a member of any of those groups
    --
    -- Example:
    --   Tuple 1: (repo, api, admin, team, engineering)  -- team has admin
    --   Tuple 2: (team, engineering, member, user, alice)  -- alice is on team
    --   Result: alice has admin on repo:api via team:engineering#member

    FOR v_path IN
        SELECT
            'group'::TEXT,
            t.relation,
            t.subject_type,
            t.subject_id,
            membership.relation,
            NULL::TEXT[]
        FROM authz.tuples t
        -- Find where user is a member of the subject (group)
        JOIN authz.tuples membership
          ON membership.namespace = t.namespace
          AND membership.resource_type = t.subject_type
          AND membership.resource_id = t.subject_id
          AND membership.relation = COALESCE(t.subject_relation, authz.default_membership_relation())
          AND membership.subject_type = 'user'
          AND membership.subject_id = p_user_id
        WHERE t.namespace = p_namespace
          AND t.resource_type = p_resource_type
          AND t.resource_id = p_resource_id
          AND t.relation = p_permission
          AND t.subject_type != 'user'  -- Groups, not direct user grants
    LOOP
        RETURN NEXT v_path;
    END LOOP;

    -- ==========================================================================
    -- PATH 3: PERMISSION HIERARCHY
    -- ==========================================================================
    -- Check if the user has a higher permission that implies this one.
    -- This requires recursion: we need to explain how they got the higher permission.
    --
    -- Example:
    --   Hierarchy: admin -> write -> read
    --   If user has 'admin', they also have 'read' via the chain [admin, write, read]
    --
    -- We recursively call explain() for each higher permission, building up
    -- the implication chain.

    FOR v_higher_permission IN
        SELECT h.permission
        FROM authz.permission_hierarchy h
        WHERE h.namespace = p_namespace
          AND h.resource_type = p_resource_type
          AND h.implies = p_permission
    LOOP
        -- Recursively explain how they got the higher permission
        FOR v_higher_path IN
            SELECT * FROM authz.explain(
                p_user_id,
                v_higher_permission,
                p_resource_type,
                p_resource_id,
                p_namespace,
                p_max_depth - 1
            )
        LOOP
            -- Build the implication chain
            IF v_higher_path.implies_chain IS NULL THEN
                v_chain := ARRAY[v_higher_permission, p_permission];
            ELSE
                v_chain := v_higher_path.implies_chain || p_permission;
            END IF;

            -- Return a hierarchy path that includes the original source
            v_path := (
                'hierarchy',
                v_higher_path.via_relation,
                v_higher_path.via_subject_type,
                v_higher_path.via_subject_id,
                v_higher_path.via_membership,
                v_chain
            );
            RETURN NEXT v_path;
        END LOOP;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql STABLE SET search_path = authz, pg_temp;

-- =============================================================================
-- EXPLAIN TEXT - Human-readable version of explain
-- =============================================================================
-- Returns a simple text description for each path, suitable for debugging
-- and audit logs.

CREATE OR REPLACE FUNCTION authz.explain_text(
    p_user_id TEXT,
    p_permission TEXT,
    p_resource_type TEXT,
    p_resource_id TEXT,
    p_namespace TEXT DEFAULT 'default'
) RETURNS SETOF TEXT AS $$
DECLARE
    v_path authz.permission_path;
    v_text TEXT;
BEGIN
    FOR v_path IN
        SELECT * FROM authz.explain(
            p_user_id, p_permission, p_resource_type, p_resource_id, p_namespace
        )
    LOOP
        CASE v_path.path_type
            WHEN 'direct' THEN
                v_text := format(
                    'DIRECT: user:%s has %s on %s:%s',
                    p_user_id, v_path.via_relation, p_resource_type, p_resource_id
                );
            WHEN 'group' THEN
                v_text := format(
                    'GROUP: user:%s is %s of %s:%s which has %s on %s:%s',
                    p_user_id, v_path.via_membership,
                    v_path.via_subject_type, v_path.via_subject_id,
                    v_path.via_relation, p_resource_type, p_resource_id
                );
            WHEN 'hierarchy' THEN
                IF v_path.via_subject_type IS NOT NULL THEN
                    v_text := format(
                        'HIERARCHY: user:%s is %s of %s:%s which has %s (%s) on %s:%s',
                        p_user_id, v_path.via_membership,
                        v_path.via_subject_type, v_path.via_subject_id,
                        v_path.via_relation,
                        array_to_string(v_path.implies_chain, ' -> '),
                        p_resource_type, p_resource_id
                    );
                ELSE
                    v_text := format(
                        'HIERARCHY: user:%s has %s (%s) on %s:%s',
                        p_user_id, v_path.via_relation,
                        array_to_string(v_path.implies_chain, ' -> '),
                        p_resource_type, p_resource_id
                    );
                END IF;
        END CASE;
        RETURN NEXT v_text;
    END LOOP;

    -- If no paths found, explain that permission is not granted
    IF NOT FOUND THEN
        RETURN NEXT format(
            'NO ACCESS: user:%s does not have %s on %s:%s',
            p_user_id, p_permission, p_resource_type, p_resource_id
        );
    END IF;

    RETURN;
END;
$$ LANGUAGE plpgsql STABLE SET search_path = authz, pg_temp;
