-- JSON Schema definitions for validating config values.
--
-- Pattern types:
--   Prefix (trailing /)  : 'flags/'               - Homogeneous collections
--   Exact (no trailing /): 'integrations/webhook' - Unique schemas
--
-- Examples:
--   Homogeneous (prefix):
--     flags/*       : All feature flags have {enabled: bool, rollout?: number}
--     rate_limits/* : All limits have {max: number, window_seconds: number}
--   Heterogeneous (exact):
--     integrations/webhook : {url, secret, headers}
--     integrations/slack   : {workspace_id, channel, bot_token}
--
-- Matching precedence:
--   1. Exact match wins over prefix
--   2. Longer prefix wins over shorter
--   3. No match = no validation required
--
-- Ownership: Platform-defined, tenant-enforced. Platform admin defines schemas,
-- all tenant writes are validated against them.

CREATE TABLE config.schemas (
    key_pattern text NOT NULL,
    schema jsonb NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (key_pattern)
);

CREATE INDEX schemas_pattern_idx ON config.schemas
    USING btree (key_pattern text_pattern_ops);

-- RLS: All tenants can read schemas, but cannot write.
-- Write access controlled at application layer via admin connection.
ALTER TABLE config.schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE config.schemas FORCE ROW LEVEL SECURITY;

CREATE POLICY schemas_read_all ON config.schemas
    FOR SELECT
    USING (true);

-- No INSERT/UPDATE/DELETE policies = tenants cannot modify via RLS
