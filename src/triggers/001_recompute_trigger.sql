-- Trigger to recompute permissions on tuple changes
--
-- BACKGROUND: Authorization as a Graph
-- =====================================
-- pg-authz models authorization as a directed graph where:
--   - Nodes are entities (users, teams, repos, documents, etc.)
--   - Edges are tuples representing relationships
--
-- Example graph:
--
--   repo:api --admin--> team:engineering --member--> user:alice
--                                        --member--> user:bob
--
-- This means: team:engineering has admin on repo:api, and alice/bob are members.
-- Therefore alice and bob should have admin on repo:api (via group expansion).
--
-- HOW CASCADING WORKS
-- ===================
-- When a tuple changes, we must recompute permissions for:
--   1. The resource in that tuple (direct change)
--   2. Any resource where this tuple's resource appears as a SUBJECT (cascade)
--
-- Example: Adding "user:alice is member of team:engineering"
--   - Tuple resource = team:engineering
--   - Step 1: Recompute team:engineering (the direct resource)
--   - Step 2: Find tuples where team:engineering is a SUBJECT
--            → Found: repo:api has team:engineering as subject
--            → Recompute repo:api so alice gets expanded as team member
--
-- WHY THIS STOPS NATURALLY
-- ========================
-- The cascade follows edges "upward" in the graph (from groups to resources).
-- It stops when we reach nodes that aren't used as subjects anywhere.
-- Typically, end-resources like repos/documents are never subjects, so cascade stops.
--
-- This works for ANY naming convention - no hardcoded "team" or "user" types.
-- The graph structure itself determines what cascades where.

-- =============================================================================
-- SMART TRIGGER ROUTING
-- =============================================================================
--
-- The trigger detects the operation type and routes to the most efficient
-- recompute strategy:
--
--   1. Single user tuple (any relation) → incremental_add/remove_user_to_group
--      - Handles both member and custom relations (admin, owner, etc.)
--      - O(R×H) where R = resources the group#relation can access
--   2. Grant to group → incremental_add_group_grant (O(G×H))
--   3. Revoke from group → incremental_remove_group_grant
--   4. Complex/batch operations → full recompute (fallback)
--
-- Statement-level trigger functions using transition tables
-- Split into separate triggers because PG doesn't allow transition tables with multi-event triggers

CREATE OR REPLACE FUNCTION authz.trigger_recompute_insert()
RETURNS TRIGGER AS $$
DECLARE
    v_count INT;
    v_tuple RECORD;
BEGIN
    -- Count tuples to decide strategy
    SELECT COUNT(*) INTO v_count FROM new_tuples;

    -- For single tuple inserts, use incremental strategy
    IF v_count = 1 THEN
        SELECT * INTO v_tuple FROM new_tuples LIMIT 1;

        IF v_tuple.subject_type = 'user' THEN
            -- User added to a group-like entity (with any relation).
            -- This handles both:
            --   - member added to team (default relation)
            --   - admin added to team (custom relation like 'admin')
            -- Both cases need to find resources where group#relation is a subject.
            PERFORM authz.incremental_add_user_to_group(
                v_tuple.resource_type,
                v_tuple.resource_id,
                v_tuple.subject_id,
                v_tuple.namespace,
                v_tuple.relation  -- Pass the actual relation (member, admin, etc.)
            );
            RETURN NULL;
        ELSE
            -- Grant to group (non-user subject)
            PERFORM authz.incremental_add_group_grant(
                v_tuple.resource_type,
                v_tuple.resource_id,
                v_tuple.relation,
                v_tuple.subject_type,
                v_tuple.subject_id,
                v_tuple.subject_relation,
                v_tuple.namespace
            );
            RETURN NULL;
        END IF;
    END IF;

    -- Fallback: full recompute for batch operations
    PERFORM authz.recompute_resource(resource_type, resource_id, namespace)
    FROM (
        -- Direct: resources that were inserted
        SELECT DISTINCT resource_type, resource_id, namespace
        FROM new_tuples

        UNION

        -- Cascade: resources where inserted tuples are subjects
        SELECT DISTINCT t.resource_type, t.resource_id, t.namespace
        FROM new_tuples n
        JOIN authz.tuples t ON t.subject_type = n.resource_type
                           AND t.subject_id = n.resource_id
                           AND t.namespace = n.namespace
    ) affected;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE OR REPLACE FUNCTION authz.trigger_recompute_update()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM authz.recompute_resource(resource_type, resource_id, namespace)
    FROM (
        -- Direct: resources from both old and new
        SELECT DISTINCT resource_type, resource_id, namespace FROM new_tuples
        UNION
        SELECT DISTINCT resource_type, resource_id, namespace FROM old_tuples

        UNION

        -- Cascade: resources where tuples are subjects
        SELECT DISTINCT t.resource_type, t.resource_id, t.namespace
        FROM new_tuples n
        JOIN authz.tuples t ON t.subject_type = n.resource_type
                           AND t.subject_id = n.resource_id
                           AND t.namespace = n.namespace
        UNION
        SELECT DISTINCT t.resource_type, t.resource_id, t.namespace
        FROM old_tuples o
        JOIN authz.tuples t ON t.subject_type = o.resource_type
                           AND t.subject_id = o.resource_id
                           AND t.namespace = o.namespace
    ) affected;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE OR REPLACE FUNCTION authz.trigger_recompute_delete()
RETURNS TRIGGER AS $$
DECLARE
    v_count INT;
    v_tuple RECORD;
BEGIN
    -- Count tuples to decide strategy
    SELECT COUNT(*) INTO v_count FROM old_tuples;

    -- For single tuple deletes, use incremental strategy
    IF v_count = 1 THEN
        SELECT * INTO v_tuple FROM old_tuples LIMIT 1;

        IF v_tuple.subject_type = 'user' THEN
            -- User removed from a group-like entity (any relation).
            -- This handles both:
            --   - member removed from team (default relation)
            --   - admin removed from team (custom relation like 'admin')
            PERFORM authz.incremental_remove_user_from_group(
                v_tuple.resource_type,
                v_tuple.resource_id,
                v_tuple.subject_id,
                v_tuple.namespace,
                v_tuple.relation  -- Pass the actual relation (member, admin, etc.)
            );
            RETURN NULL;
        ELSE
            -- Revoke from group (non-user subject)
            PERFORM authz.incremental_remove_group_grant(
                v_tuple.resource_type,
                v_tuple.resource_id,
                v_tuple.relation,
                v_tuple.subject_type,
                v_tuple.subject_id,
                v_tuple.subject_relation,  -- Pass subject_relation (e.g., 'admin' vs 'member')
                v_tuple.namespace
            );
            RETURN NULL;
        END IF;
    END IF;

    -- Fallback: full recompute for batch operations
    PERFORM authz.recompute_resource(resource_type, resource_id, namespace)
    FROM (
        -- Direct: resources that were deleted
        SELECT DISTINCT resource_type, resource_id, namespace
        FROM old_tuples

        UNION

        -- Cascade: resources where deleted tuples were subjects
        SELECT DISTINCT t.resource_type, t.resource_id, t.namespace
        FROM old_tuples o
        JOIN authz.tuples t ON t.subject_type = o.resource_type
                           AND t.subject_id = o.resource_id
                           AND t.namespace = o.namespace
    ) affected;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

-- Separate triggers for each event type
CREATE TRIGGER recompute_on_tuple_insert
AFTER INSERT ON authz.tuples
REFERENCING NEW TABLE AS new_tuples
FOR EACH STATEMENT EXECUTE FUNCTION authz.trigger_recompute_insert();

CREATE TRIGGER recompute_on_tuple_update
AFTER UPDATE ON authz.tuples
REFERENCING NEW TABLE AS new_tuples OLD TABLE AS old_tuples
FOR EACH STATEMENT EXECUTE FUNCTION authz.trigger_recompute_update();

CREATE TRIGGER recompute_on_tuple_delete
AFTER DELETE ON authz.tuples
REFERENCING OLD TABLE AS old_tuples
FOR EACH STATEMENT EXECUTE FUNCTION authz.trigger_recompute_delete();

-- =============================================================================
-- PERMISSION HIERARCHY TRIGGER
-- =============================================================================
--
-- WHAT THIS DOES
-- ==============
-- When you change the permission_hierarchy table (add/remove rules like
-- "admin implies write"), this trigger automatically recomputes permissions
-- for ALL resources of that type.
--
-- Example: You add ('repo', 'admin', 'read')
--   → Every repo in the system gets recomputed
--   → Users with 'admin' now also have 'read' in the computed table
--
-- WHY AUTOMATIC RECOMPUTE
-- =======================
-- Wrong permissions are worse than slow permissions. If you add a hierarchy
-- rule and permissions don't update, that's a security bug. Automatic
-- recompute ensures correctness.
--
-- PERFORMANCE IMPLICATIONS
-- ========================
-- This operation can be SLOW for large datasets:
--   - 10,000 repos: ~1-5 seconds
--   - 100,000 repos: ~10-30 seconds
--   - 1,000,000 repos: ~1-5 minutes
--
-- During recompute:
--   - The session that made the change BLOCKS until complete
--   - Other reads continue normally (MVCC)
--   - Other writes to the SAME resource type may wait for row locks
--   - Other writes to DIFFERENT resource types continue normally
--
-- BEST PRACTICES
-- ==============
-- 1. Define hierarchy rules BEFORE adding tuples (no recompute needed)
-- 2. For existing data, make hierarchy changes during low-traffic periods
-- 3. Hierarchy changes should be rare (schema-level decisions, not daily ops)
-- 4. Test hierarchy changes in staging first to measure impact

CREATE OR REPLACE FUNCTION authz.trigger_hierarchy_insert()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM authz.recompute_resource(t.resource_type, t.resource_id, t.namespace)
    FROM (
        SELECT DISTINCT resource_type, resource_id, namespace
        FROM authz.tuples
        WHERE (resource_type, namespace) IN (
            SELECT resource_type, namespace FROM new_hierarchy
        )
    ) t;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE OR REPLACE FUNCTION authz.trigger_hierarchy_update()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM authz.recompute_resource(t.resource_type, t.resource_id, t.namespace)
    FROM (
        SELECT DISTINCT resource_type, resource_id, namespace
        FROM authz.tuples
        WHERE (resource_type, namespace) IN (
            SELECT resource_type, namespace FROM new_hierarchy
            UNION
            SELECT resource_type, namespace FROM old_hierarchy
        )
    ) t;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE OR REPLACE FUNCTION authz.trigger_hierarchy_delete()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM authz.recompute_resource(t.resource_type, t.resource_id, t.namespace)
    FROM (
        SELECT DISTINCT resource_type, resource_id, namespace
        FROM authz.tuples
        WHERE (resource_type, namespace) IN (
            SELECT resource_type, namespace FROM old_hierarchy
        )
    ) t;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE TRIGGER recompute_on_hierarchy_insert
AFTER INSERT ON authz.permission_hierarchy
REFERENCING NEW TABLE AS new_hierarchy
FOR EACH STATEMENT EXECUTE FUNCTION authz.trigger_hierarchy_insert();

CREATE TRIGGER recompute_on_hierarchy_update
AFTER UPDATE ON authz.permission_hierarchy
REFERENCING NEW TABLE AS new_hierarchy OLD TABLE AS old_hierarchy
FOR EACH STATEMENT EXECUTE FUNCTION authz.trigger_hierarchy_update();

CREATE TRIGGER recompute_on_hierarchy_delete
AFTER DELETE ON authz.permission_hierarchy
REFERENCING OLD TABLE AS old_hierarchy
FOR EACH STATEMENT EXECUTE FUNCTION authz.trigger_hierarchy_delete();

-- =============================================================================
-- HIERARCHY CYCLE PREVENTION
-- =============================================================================
-- Prevent cycles in permission hierarchy at write time (fail fast).
-- A cycle like admin -> write -> read -> admin would cause infinite loops in recompute.
-- Uses recursive CTE to handle branching hierarchies (permission can imply multiple things).

CREATE OR REPLACE FUNCTION authz.check_hierarchy_cycle()
RETURNS TRIGGER AS $$
BEGIN
    -- Check if adding this edge creates a cycle using recursive CTE
    -- We look for any path from NEW.implies back to NEW.permission
    IF EXISTS (
        WITH RECURSIVE reachable AS (
            -- Start from what the new permission implies
            SELECT NEW.implies AS permission, 1 AS depth

            UNION

            -- Follow existing implications (handles branching)
            SELECT h.implies, r.depth + 1
            FROM reachable r
            JOIN authz.permission_hierarchy h
              ON h.namespace = NEW.namespace
              AND h.resource_type = NEW.resource_type
              AND h.permission = r.permission
            WHERE r.depth < 100  -- Safety limit
        )
        SELECT 1 FROM reachable WHERE permission = NEW.permission
    ) THEN
        RAISE EXCEPTION 'Hierarchy cycle detected: % -> % would create a cycle',
            NEW.permission, NEW.implies;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE TRIGGER prevent_hierarchy_cycle
BEFORE INSERT OR UPDATE ON authz.permission_hierarchy
FOR EACH ROW EXECUTE FUNCTION authz.check_hierarchy_cycle();
