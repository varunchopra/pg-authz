-- =============================================================================
-- SCHEMA AND TABLES FOR POSTKIT/AUTHZ
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS authz;

-- =============================================================================
-- TUPLES TABLE
-- =============================================================================
-- The source of truth for all relationships.
-- Format: (resource_type, resource_id) has relation to (subject_type, subject_id)
--
-- Examples:
--   Direct grant: (doc, 123, viewer, user, alice, NULL)
--   Group grant:  (doc, 123, editor, team, engineering, NULL)
--   Group member: (team, engineering, member, user, alice, NULL)
--   Nested team:  (team, platform, member, team, infrastructure, NULL)
--   Userset:      (repo, api, admin, team, engineering, admin)
CREATE TABLE authz.tuples (
    id bigserial PRIMARY KEY,
    namespace text NOT NULL DEFAULT 'default',
    resource_type text NOT NULL,
    resource_id text NOT NULL,
    relation text NOT NULL,
    subject_type text NOT NULL,
    subject_id text NOT NULL,
    subject_relation text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz DEFAULT NULL
);

-- Uniqueness constraint treating NULL and '' as equivalent for subject_relation
CREATE UNIQUE INDEX tuples_unique_idx ON authz.tuples (namespace, resource_type, resource_id, relation, subject_type, subject_id, COALESCE(subject_relation, ''));

-- =============================================================================
-- PERMISSION HIERARCHY TABLE
-- =============================================================================
-- Defines permission implications: having 'permission' implies having 'implies'
-- Example: admin -> write -> read
CREATE TABLE authz.permission_hierarchy (
    id bigserial PRIMARY KEY,
    namespace text NOT NULL DEFAULT 'default',
    resource_type text NOT NULL,
    permission text NOT NULL,
    implies text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (namespace, resource_type, permission, implies)
);

-- =============================================================================
-- ROW-LEVEL SECURITY
-- =============================================================================
ALTER TABLE authz.tuples ENABLE ROW LEVEL SECURITY;

ALTER TABLE authz.tuples FORCE ROW LEVEL SECURITY;

ALTER TABLE authz.permission_hierarchy ENABLE ROW LEVEL SECURITY;

ALTER TABLE authz.permission_hierarchy FORCE ROW LEVEL SECURITY;

CREATE POLICY tuples_tenant_isolation ON authz.tuples
    USING (namespace = current_setting('authz.tenant_id', TRUE))
    WITH CHECK (namespace = current_setting('authz.tenant_id', TRUE));

CREATE POLICY hierarchy_tenant_isolation ON authz.permission_hierarchy
    USING (namespace = current_setting('authz.tenant_id', TRUE))
    WITH CHECK (namespace = current_setting('authz.tenant_id', TRUE));
