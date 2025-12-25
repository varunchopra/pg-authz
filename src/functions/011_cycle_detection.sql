-- =============================================================================
-- CYCLE DETECTION
-- =============================================================================
-- Prevents and detects circular group memberships.
--
-- Cycles are bad because they cause infinite recursion during permission
-- checks. Example cycle: team:A contains team:B contains team:C contains team:A
--
-- would_create_cycle() is called before inserting group-to-group memberships.
-- detect_cycles() is a maintenance tool to find cycles if they somehow exist.


-- Check if adding a membership would create a cycle
--
-- Called before inserting: (parent, member, child) tuples where child is a group.
-- Returns true if p_parent is already a descendant of p_child (which would
-- make adding p_child as a member of p_parent create a cycle).
CREATE OR REPLACE FUNCTION authz.would_create_cycle(
    p_parent_type text,
    p_parent_id text,
    p_child_type text,
    p_child_id text,
    p_namespace text DEFAULT 'default'
)
RETURNS boolean AS $$
    WITH RECURSIVE ancestors AS (
        -- Start from the proposed parent
        SELECT
            p_parent_type AS group_type,
            p_parent_id AS group_id,
            1 AS depth

        UNION

        -- Walk up: find groups that contain the current group
        SELECT
            t.resource_type,
            t.resource_id,
            a.depth + 1
        FROM ancestors a
        JOIN authz.tuples t
          ON t.namespace = p_namespace
          AND t.subject_type = a.group_type
          AND t.subject_id = a.group_id
          AND t.relation = 'member'
        WHERE a.depth < authz.max_group_depth()
    )
    -- Cycle exists if child appears in parent's ancestor chain
    SELECT EXISTS (
        SELECT 1 FROM ancestors
        WHERE group_type = p_child_type AND group_id = p_child_id
    );
$$ LANGUAGE sql STABLE SET search_path = authz, pg_temp;


-- Find existing cycles in the group membership graph
--
-- Use this to diagnose problems if cycles somehow get created (e.g., by
-- direct SQL inserts bypassing write_tuple validation).
--
-- Returns the path of each cycle found.
CREATE OR REPLACE FUNCTION authz.detect_cycles(p_namespace text DEFAULT 'default')
RETURNS TABLE(cycle_path text[]) AS $$
    WITH RECURSIVE
    -- All group-to-group membership edges
    group_edges AS (
        SELECT
            resource_type AS parent_type,
            resource_id AS parent_id,
            subject_type AS child_type,
            subject_id AS child_id
        FROM authz.tuples
        WHERE namespace = p_namespace
          AND relation = 'member'
          AND subject_type != 'user'
    ),

    -- Explore all paths, detecting when we revisit a node
    paths AS (
        SELECT
            parent_type,
            parent_id,
            child_type,
            child_id,
            ARRAY[parent_type || ':' || parent_id, child_type || ':' || child_id] AS path,
            (parent_type = child_type AND parent_id = child_id) AS is_cycle
        FROM group_edges

        UNION ALL

        SELECT
            p.parent_type,
            p.parent_id,
            e.child_type,
            e.child_id,
            p.path || (e.child_type || ':' || e.child_id),
            (e.child_type || ':' || e.child_id) = ANY(p.path)
        FROM paths p
        JOIN group_edges e
          ON e.parent_type = p.child_type
          AND e.parent_id = p.child_id
        WHERE NOT p.is_cycle
          AND array_length(p.path, 1) < authz.max_group_depth()
    )

    SELECT DISTINCT path AS cycle_path
    FROM paths
    WHERE is_cycle;
$$ LANGUAGE sql STABLE SET search_path = authz, pg_temp;
