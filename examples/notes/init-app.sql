-- App-specific tables for the authz demo
-- Multi-tenant architecture: orgs contain notes and teams

-- =============================================================================
-- ORGANIZATIONS
-- =============================================================================

-- Organizations table
CREATE TABLE IF NOT EXISTS orgs (
    org_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,  -- URL-friendly identifier
    owner_id TEXT NOT NULL,     -- user_id of creator
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orgs_slug ON orgs(slug);
CREATE INDEX IF NOT EXISTS idx_orgs_owner ON orgs(owner_id);

-- Organization memberships (who belongs to which org)
CREATE TABLE IF NOT EXISTS org_memberships (
    membership_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    org_id TEXT NOT NULL REFERENCES orgs(org_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT org_memberships_unique UNIQUE (org_id, user_id),
    CONSTRAINT org_memberships_role_valid CHECK (role IN ('owner', 'admin', 'member'))
);

CREATE INDEX IF NOT EXISTS idx_org_memberships_user ON org_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_org_memberships_org ON org_memberships(org_id);

-- Organization invites (for joining orgs)
CREATE TABLE IF NOT EXISTS org_invites (
    invite_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    org_id TEXT NOT NULL REFERENCES orgs(org_id) ON DELETE CASCADE,
    code TEXT NOT NULL UNIQUE,
    email TEXT,  -- NULL for link-based invites (anyone with link can join)
    role TEXT NOT NULL DEFAULT 'member',
    created_by TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT org_invites_role_valid CHECK (role IN ('admin', 'member'))
);

CREATE INDEX IF NOT EXISTS idx_org_invites_code ON org_invites(code);
CREATE INDEX IF NOT EXISTS idx_org_invites_org ON org_invites(org_id);

-- =============================================================================
-- CONTENT TABLES (org-scoped)
-- =============================================================================

-- Notes table (content storage - permissions managed via authz tuples)
CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    org_id TEXT REFERENCES orgs(org_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    owner_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notes_owner ON notes(owner_id);
CREATE INDEX IF NOT EXISTS idx_notes_org ON notes(org_id);

-- Teams table (for team-based sharing within an org)
CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    org_id TEXT REFERENCES orgs(org_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_teams_owner ON teams(owner_id);
CREATE INDEX IF NOT EXISTS idx_teams_org ON teams(org_id);

-- =============================================================================
-- PERMISSION HIERARCHIES (set up per-org when org is created)
-- =============================================================================
-- Note: These are set up dynamically when creating an org via:
--   authz.add_hierarchy('note', 'owner', 'edit', 'org:{org_id}')
--   authz.add_hierarchy('note', 'edit', 'view', 'org:{org_id}')
--   authz.add_hierarchy('team', 'owner', 'admin', 'org:{org_id}')
--   authz.add_hierarchy('team', 'admin', 'member', 'org:{org_id}')
--   authz.add_hierarchy('org', 'owner', 'admin', 'org:{org_id}')
--   authz.add_hierarchy('org', 'admin', 'member', 'org:{org_id}')

-- Legacy hierarchies for backward compatibility (will be removed)
SELECT authz.add_hierarchy('system', 'superadmin', 'admin', 'default');
SELECT authz.add_hierarchy('system', 'admin', 'user', 'default');
SELECT authz.add_hierarchy('note', 'owner', 'edit', 'default');
SELECT authz.add_hierarchy('note', 'edit', 'view', 'default');
SELECT authz.add_hierarchy('team', 'owner', 'admin', 'default');
SELECT authz.add_hierarchy('team', 'admin', 'member', 'default');
