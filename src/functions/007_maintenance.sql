-- =============================================================================
-- MAINTENANCE FUNCTIONS
-- =============================================================================
-- Functions for bulk operations, consistency checking, and repair.

-- =============================================================================
-- BULK OPERATION SUPPORT
-- =============================================================================
-- For importing large datasets, disable triggers, bulk insert, then recompute.
-- Pattern: disable_triggers() → INSERT many tuples → recompute_all() → enable_triggers()

CREATE OR REPLACE FUNCTION authz.disable_recompute_triggers()
RETURNS VOID AS $$
BEGIN
    ALTER TABLE authz.tuples DISABLE TRIGGER recompute_on_tuple_insert;
    ALTER TABLE authz.tuples DISABLE TRIGGER recompute_on_tuple_update;
    ALTER TABLE authz.tuples DISABLE TRIGGER recompute_on_tuple_delete;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

CREATE OR REPLACE FUNCTION authz.enable_recompute_triggers()
RETURNS VOID AS $$
BEGIN
    ALTER TABLE authz.tuples ENABLE TRIGGER recompute_on_tuple_insert;
    ALTER TABLE authz.tuples ENABLE TRIGGER recompute_on_tuple_update;
    ALTER TABLE authz.tuples ENABLE TRIGGER recompute_on_tuple_delete;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

-- =============================================================================
-- CONSISTENCY CHECK
-- =============================================================================
-- Verify the computed table matches what tuples say it should be.
-- Essential for operational confidence after bulk operations or incidents.
--
-- This does a full recompute-and-compare which is expensive but accurate.
-- For large namespaces, run during maintenance windows.
--
-- CONCURRENCY NOTE
-- ----------------
-- This function does NOT acquire locks. If writes occur during verification,
-- results may include false positives (reported as missing/extra but actually
-- being updated concurrently). For authoritative verification:
--   1. Run during maintenance windows with writes paused, OR
--   2. Accept that results are a point-in-time snapshot with possible races

CREATE OR REPLACE FUNCTION authz.verify_computed(
    p_namespace TEXT DEFAULT 'default'
) RETURNS TABLE(
    resource_type TEXT,
    resource_id TEXT,
    status TEXT,
    details TEXT
) AS $$
DECLARE
    v_resource RECORD;
    v_expected RECORD;
    v_actual RECORD;
    v_mismatch BOOLEAN;
    v_rows INT;
BEGIN
    -- Create temp table once (more efficient than CREATE/DROP in loop)
    CREATE TEMP TABLE _verify_expected (
        permission TEXT,
        user_id TEXT,
        UNIQUE (permission, user_id)
    ) ON COMMIT DROP;

    -- Check each resource that has tuples
    FOR v_resource IN
        SELECT DISTINCT t.resource_type, t.resource_id
        FROM authz.tuples t
        WHERE t.namespace = p_namespace
    LOOP
        -- Clear temp table for this resource
        TRUNCATE _verify_expected;

        -- Phase 1: Direct permissions
        INSERT INTO _verify_expected (permission, user_id)
        SELECT DISTINCT t.relation, t.subject_id
        FROM authz.tuples t
        WHERE t.namespace = p_namespace
          AND t.resource_type = v_resource.resource_type
          AND t.resource_id = v_resource.resource_id
          AND t.subject_type = 'user'
          AND t.subject_relation IS NULL;

        -- Phase 2: Group expansion
        INSERT INTO _verify_expected (permission, user_id)
        SELECT DISTINCT t.relation, membership.subject_id
        FROM authz.tuples t
        JOIN authz.tuples membership
          ON membership.namespace = t.namespace
          AND membership.resource_type = t.subject_type
          AND membership.resource_id = t.subject_id
          AND membership.relation = COALESCE(t.subject_relation, authz.default_membership_relation())
          AND membership.subject_type = 'user'
        WHERE t.namespace = p_namespace
          AND t.resource_type = v_resource.resource_type
          AND t.resource_id = v_resource.resource_id
          AND t.subject_type != 'user'
        ON CONFLICT (permission, user_id) DO NOTHING;

        -- Phase 3: Hierarchy expansion (fixed-point)
        LOOP
            INSERT INTO _verify_expected (permission, user_id)
            SELECT DISTINCT h.implies, e.user_id
            FROM _verify_expected e
            JOIN authz.permission_hierarchy h
              ON h.namespace = p_namespace
              AND h.resource_type = v_resource.resource_type
              AND h.permission = e.permission
            ON CONFLICT (permission, user_id) DO NOTHING;

            GET DIAGNOSTICS v_rows = ROW_COUNT;
            EXIT WHEN v_rows = 0;
        END LOOP;

        -- Compare expected vs actual
        v_mismatch := FALSE;

        -- Check for missing entries (expected but not in computed)
        FOR v_expected IN
            SELECT e.permission, e.user_id
            FROM _verify_expected e
            WHERE NOT EXISTS (
                SELECT 1 FROM authz.computed c
                WHERE c.namespace = p_namespace
                  AND c.resource_type = v_resource.resource_type
                  AND c.resource_id = v_resource.resource_id
                  AND c.permission = e.permission
                  AND c.user_id = e.user_id
            )
        LOOP
            resource_type := v_resource.resource_type;
            resource_id := v_resource.resource_id;
            status := 'missing';
            details := format('Expected %s:%s but not in computed', v_expected.permission, v_expected.user_id);
            RETURN NEXT;
            v_mismatch := TRUE;
        END LOOP;

        -- Check for extra entries (in computed but not expected)
        FOR v_actual IN
            SELECT c.permission, c.user_id
            FROM authz.computed c
            WHERE c.namespace = p_namespace
              AND c.resource_type = v_resource.resource_type
              AND c.resource_id = v_resource.resource_id
              AND NOT EXISTS (
                SELECT 1 FROM _verify_expected e
                WHERE e.permission = c.permission
                  AND e.user_id = c.user_id
            )
        LOOP
            resource_type := v_resource.resource_type;
            resource_id := v_resource.resource_id;
            status := 'extra';
            details := format('Found %s:%s in computed but not expected', v_actual.permission, v_actual.user_id);
            RETURN NEXT;
            v_mismatch := TRUE;
        END LOOP;
    END LOOP;

    -- Check for orphaned computed entries (resources with no tuples)
    FOR v_resource IN
        SELECT DISTINCT c.resource_type, c.resource_id
        FROM authz.computed c
        WHERE c.namespace = p_namespace
          AND NOT EXISTS (
              SELECT 1 FROM authz.tuples t
              WHERE t.namespace = c.namespace
                AND t.resource_type = c.resource_type
                AND t.resource_id = c.resource_id
          )
    LOOP
        resource_type := v_resource.resource_type;
        resource_id := v_resource.resource_id;
        status := 'orphaned';
        details := 'Computed entries exist but no tuples for this resource';
        RETURN NEXT;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

-- Repair computed table by recomputing all resources
CREATE OR REPLACE FUNCTION authz.repair_computed(
    p_namespace TEXT DEFAULT 'default'
) RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    -- Simply delegate to recompute_all which rebuilds everything
    SELECT authz.recompute_all(p_namespace) INTO v_count;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql SET search_path = authz, pg_temp;

-- =============================================================================
-- STATISTICS
-- =============================================================================
-- Returns namespace statistics for monitoring and capacity planning.
--
-- METRICS EXPLAINED
-- -----------------
-- tuple_count: Number of relationship tuples (grants, memberships)
-- computed_count: Number of pre-computed permission entries
-- hierarchy_rule_count: Number of permission implication rules
-- amplification_factor: computed_count / tuple_count (write amplification)
-- unique_users: Number of distinct users with any permission
-- unique_resources: Number of distinct resources with any permission
--
-- USAGE
-- -----
-- Monitor amplification_factor: If it grows too large (>100x), consider
-- whether you have very large groups or deep hierarchies.

CREATE OR REPLACE FUNCTION authz.get_stats(
    p_namespace TEXT DEFAULT 'default'
) RETURNS TABLE(
    tuple_count BIGINT,
    computed_count BIGINT,
    hierarchy_rule_count BIGINT,
    amplification_factor NUMERIC,
    unique_users BIGINT,
    unique_resources BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*) FROM authz.tuples WHERE namespace = p_namespace)::BIGINT,
        (SELECT COUNT(*) FROM authz.computed WHERE namespace = p_namespace)::BIGINT,
        (SELECT COUNT(*) FROM authz.permission_hierarchy WHERE namespace = p_namespace)::BIGINT,
        ROUND(
            (SELECT COUNT(*) FROM authz.computed WHERE namespace = p_namespace)::NUMERIC /
            NULLIF((SELECT COUNT(*) FROM authz.tuples WHERE namespace = p_namespace), 0),
            2
        ),
        (SELECT COUNT(DISTINCT user_id) FROM authz.computed WHERE namespace = p_namespace)::BIGINT,
        (SELECT COUNT(DISTINCT (resource_type, resource_id)) FROM authz.computed WHERE namespace = p_namespace)::BIGINT;
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE SET search_path = authz, pg_temp;
