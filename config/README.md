# config

Versioned configuration storage. Handles prompts, feature flags, secrets, settings — all with version history and instant rollback.

## Install

See [installation instructions](../README.md#install) in the main README.

## Quick Start

```sql
-- Store a prompt (creates version 1, activates it)
SELECT config.set('prompts/support-bot', '{
    "template": "You are a helpful support agent...",
    "model": "claude-sonnet-4-20250514",
    "temperature": 0.7
}');

-- Get active version
SELECT * FROM config.get('prompts/support-bot');

-- Update (creates version 2, activates it)
SELECT config.set('prompts/support-bot', '{
    "template": "You are an expert support agent...",
    "model": "claude-sonnet-4-20250514",
    "temperature": 0.5
}');

-- Rollback to version 1
SELECT config.rollback('prompts/support-bot');

-- Or activate specific version
SELECT config.activate('prompts/support-bot', 2);
```

## Key Naming Conventions

Use prefixes to organize your configuration:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `prompts/` | LLM system prompts | `prompts/support-bot`, `prompts/sales-assistant` |
| `flags/` | Feature flags | `flags/new-checkout`, `flags/dark-mode` |
| `secrets/` | API keys, tokens | `secrets/OPENAI_API_KEY`, `secrets/stripe_live` |
| `settings/` | App configuration | `settings/email`, `settings/limits` |

### Prompts

```sql
SELECT config.set('prompts/support-bot', '{
    "template": "You are a helpful support agent for {{company}}...",
    "model": "claude-sonnet-4-20250514",
    "temperature": 0.7,
    "max_tokens": 1000
}');

-- List all prompts
SELECT * FROM config.list('prompts/');
```

### Feature Flags

```sql
SELECT config.set('flags/new-checkout', '{
    "enabled": true,
    "rollout": 0.5,
    "allowlist": ["user-123", "user-456"]
}');

-- Get just the rollout value (partial read)
SELECT config.get_path('flags/new-checkout', ARRAY['rollout']);

-- Update just the rollout (partial update, creates new version)
SELECT config.merge('flags/new-checkout', '{"rollout": 0.75}');

-- Find all enabled flags
SELECT * FROM config.search('{"enabled": true}', 'flags/');
```

### Secrets

Caller encrypts before storing. Postkit never sees plaintext.

```sql
SELECT config.set('secrets/OPENAI_API_KEY', '{
    "encrypted": "aes256gcm:nonce:ciphertext",
    "key_id": "key-2024-01"
}');
```

### Settings

```sql
SELECT config.set('settings/email', '{
    "from": "support@acme.com",
    "reply_to": "help@acme.com"
}');

SELECT config.set('settings/limits', '{
    "max_upload_mb": 100,
    "rate_limit_rpm": 60
}');
```

## Batch Operations

```sql
-- Load multiple configs in one query (app startup)
SELECT * FROM config.get_batch(ARRAY['prompts/bot-a', 'prompts/bot-b', 'flags/checkout']);

-- Search by content
SELECT * FROM config.search('{"model": "claude-sonnet-4-20250514"}', 'prompts/');
```

## Partial Reads & Updates

```sql
-- Read single field (avoids transferring entire blob)
SELECT config.get_path('prompts/bot', ARRAY['temperature']);
SELECT config.get_path('settings/limits', ARRAY['max_upload_mb']);

-- Update single field (creates new version, preserves other fields)
SELECT config.merge('prompts/bot', '{"temperature": 0.8}');
SELECT config.merge('flags/checkout', '{"rollout": 0.75, "enabled": true}');
```

## Version History

```sql
-- See all versions
SELECT * FROM config.history('prompts/support-bot');

-- Get specific version
SELECT * FROM config.get('prompts/support-bot', 3);

-- Delete old version (cannot delete active)
SELECT config.delete_version('prompts/support-bot', 1);

-- Cleanup old versions (keep last 10 per key)
SELECT config.cleanup_old_versions(10);
```

See [docs/config/](../docs/config/) for full API reference.
