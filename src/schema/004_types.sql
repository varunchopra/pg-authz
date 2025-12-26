-- =============================================================================
-- CUSTOM TYPES
-- =============================================================================
--
-- Types used by authorization functions.
--
-- =============================================================================

-- Return type for explain results
-- Used by authz.explain() to describe how a user got a permission
CREATE TYPE authz.permission_path AS (
    path_type text,        -- 'direct', 'group', 'hierarchy', or 'resource'
    via_relation text,     -- The relation that granted access (e.g., 'admin')
    via_subject_type text, -- For group/hierarchy: the group type (e.g., 'team')
                           -- For resource: the ancestor resource type (e.g., 'folder')
    via_subject_id text,   -- For group/hierarchy: the group id (e.g., 'engineering')
                           -- For resource: the ancestor resource id (e.g., 'projects')
    via_membership text,   -- For group/hierarchy: user's relation to group (e.g., 'member')
    path_chain text[]      -- Path traversed (usage depends on path_type):
                           --   'group': nested group chain, e.g., ['team:infra', 'team:platform']
                           --   'hierarchy': permission chain, e.g., ['admin', 'write', 'read']
                           --   'resource': resource chain, e.g., ['folder:projects', 'folder:root']
                           --   'direct': NULL
);
