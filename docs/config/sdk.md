<!-- AUTO-GENERATED. DO NOT EDIT. Run `make docs` to regenerate. -->

# Config Python SDK

### activate

```python
activate(key: str, version: int) -> bool
```

Activate a specific version.

**Parameters:**
- `key`: Config key
- `version`: Version to activate

**Returns:** True if version was found and activated

*Source: sdk/src/postkit/config/client.py:194*

---

### cleanup_old_versions

```python
cleanup_old_versions(keep_versions: int = 10) -> int
```

Delete old inactive versions, keeping N most recent per key.

**Parameters:**
- `keep_versions`: Number of inactive versions to keep per key (default 10)

**Returns:** Count of versions deleted

*Source: sdk/src/postkit/config/client.py:316*

---

### clear_actor

```python
clear_actor() -> None
```

Clear actor context.

*Source: sdk/src/postkit/base.py:325*

---

### delete

```python
delete(key: str) -> int
```

Delete all versions of a config entry.

**Parameters:**
- `key`: Config key

**Returns:** Count of versions deleted

*Source: sdk/src/postkit/config/client.py:261*

---

### delete_version

```python
delete_version(key: str, version: int) -> bool
```

Delete a specific version (cannot delete active version).

**Parameters:**
- `key`: Config key
- `version`: Version to delete

**Returns:** True if deleted

*Source: sdk/src/postkit/config/client.py:274*

---

### exists

```python
exists(key: str) -> bool
```

Check if a config key exists.

**Parameters:**
- `key`: Config key

**Returns:** True if key exists and has an active version

*Source: sdk/src/postkit/config/client.py:290*

---

### get

```python
get(key: str, version: int | None = None) -> dict | None
```

Get config entry.

**Parameters:**
- `key`: Config key
- `version`: Specific version (default: active version)

**Returns:** Dict with 'value', 'version', 'created_at' or None if not found

*Source: sdk/src/postkit/config/client.py:85*

---

### get_audit_events

```python
get_audit_events(limit: int = 100, event_type: str | None = None, key: str | None = None) -> list[dict]
```

Query audit events.

**Parameters:**
- `limit`: Maximum number of events to return (default 100)
- `event_type`: Filter by event type (e.g., 'entry_created', 'entry_deleted')
- `key`: Filter by config key

**Returns:** List of audit event dictionaries

*Source: sdk/src/postkit/config/client.py:331*

---

### get_batch

```python
get_batch(keys: list[str]) -> list[dict]
```

Get multiple config entries in one query.

**Parameters:**
- `keys`: List of config keys to fetch

**Returns:** List of dicts with 'key', 'value', 'version', 'created_at'

*Source: sdk/src/postkit/config/client.py:115*

---

### get_path

```python
get_path(key: str, *path: str) -> Any
```

Get a specific path within a config value.

**Parameters:**
- `key`: Config key *path: Path segments (e.g., "model", "name" for {"model": {"name": ...}})

**Returns:** The value at the path, or None if not found

**Example:**
```python
config.get_path("prompts/bot", "temperature")
config.get_path("flags/checkout", "rollout")
config.get_path("settings/model", "params", "temperature")
```

*Source: sdk/src/postkit/config/client.py:129*

---

### get_stats

```python
get_stats() -> dict
```

Get namespace statistics.

**Returns:** Dict with 'total_keys', 'total_versions', 'keys_by_prefix'

*Source: sdk/src/postkit/config/client.py:301*

---

### get_value

```python
get_value(key: str, default: Any = None) -> Any
```

Get just the value (convenience method).

**Parameters:**
- `key`: Config key
- `default`: Default value if key doesn't exist

**Returns:** The config value, or default if not found

*Source: sdk/src/postkit/config/client.py:100*

---

### history

```python
history(key: str, limit: int = 50) -> list[dict]
```

Get version history for a key.

**Parameters:**
- `key`: Config key
- `limit`: Max versions to return

**Returns:** List of dicts with 'version', 'value', 'is_active', 'created_at', 'created_by'

*Source: sdk/src/postkit/config/client.py:246*

---

### list

```python
list(prefix: str | None = None, limit: int = 100, cursor: str | None = None) -> list[dict]
```

List active config entries.

**Parameters:**
- `prefix`: Filter by key prefix (e.g., 'prompts/')
- `limit`: Max results (default 100, max 1000)
- `cursor`: Pagination cursor (last key from previous page)

**Returns:** List of dicts with 'key', 'value', 'version', 'created_at'

*Source: sdk/src/postkit/config/client.py:225*

---

### merge

```python
merge(key: str, changes: dict) -> int
```

Merge changes into config, creating new version.

**Parameters:**
- `key`: Config key
- `changes`: Dict of fields to merge

**Returns:** New version number

**Example:**
```python
config.merge("flags/checkout", {"rollout": 0.75})
config.merge("prompts/bot", {"temperature": 0.8, "max_tokens": 2000})
```

*Source: sdk/src/postkit/config/client.py:149*

---

### rollback

```python
rollback(key: str) -> int | None
```

Rollback to previous version.

**Parameters:**
- `key`: Config key

**Returns:** New active version number, or None if no previous version

*Source: sdk/src/postkit/config/client.py:210*

---

### search

```python
search(contains: dict, prefix: str | None = None, limit: int = 100) -> list[dict]
```

Find configs where value contains given JSON.

**Parameters:**
- `contains`: JSON object to search for (uses containment)
- `prefix`: Optional key prefix filter
- `limit`: Max results (default 100)

**Returns:** List of dicts with 'key', 'value', 'version', 'created_at'

**Example:**
```python
config.search({"enabled": True})  # All enabled flags
config.search({"model": "claude-sonnet-4-20250514"}, prefix="prompts/")
```

*Source: sdk/src/postkit/config/client.py:172*

---

### set

```python
set(key: str, value: Any) -> int
```

Create a new version and activate it.

**Parameters:**
- `key`: Config key (e.g., 'prompts/support-bot', 'flags/checkout')
- `value`: Config value (will be stored as JSONB)

**Returns:** New version number

*Source: sdk/src/postkit/config/client.py:69*

---

### set_actor

```python
set_actor(actor_id: str | None = None, request_id: str | None = None, on_behalf_of: str | None = None, reason: str | None = None) -> None
```

Set actor context for audit logging. Only updates fields that are passed.

**Parameters:**
- `actor_id`: The actor making changes (e.g., 'user:alice', 'service:billing')
- `request_id`: Request/correlation ID for tracing
- `on_behalf_of`: Principal being represented (e.g., 'user:customer')
- `reason`: Reason for the action (e.g., 'support_ticket:123')

**Example:**
```python
client.clear_actor()
client.set_actor(request_id="req-123")  # Set request context first
client.set_actor(actor_id="user:alice")  # Add actor after auth
```

*Source: sdk/src/postkit/base.py:296*

---
