-- =============================================================================
-- INDEXES FOR POSTKIT/CONFIG
-- =============================================================================

-- Enforce single active version per key (prevents race condition in set())
CREATE UNIQUE INDEX entries_single_active_idx ON config.entries (namespace, key)
    WHERE is_active = true;

-- Version history for a key
CREATE INDEX entries_key_versions_idx ON config.entries (namespace, key, version DESC);

-- List all active entries (for config.list())
CREATE INDEX entries_namespace_active_idx ON config.entries (namespace, created_at DESC)
    WHERE is_active = true;

-- Prefix queries (for config.list('prompts/'))
CREATE INDEX entries_key_prefix_idx ON config.entries (namespace, key text_pattern_ops)
    WHERE is_active = true;

-- Content search (for config.search())
CREATE INDEX entries_value_gin_idx ON config.entries USING gin (value jsonb_path_ops)
    WHERE is_active = true;
