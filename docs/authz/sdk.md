<!-- AUTO-GENERATED. DO NOT EDIT. Run `make docs` to regenerate. -->

# Authz Python SDK

### add_hierarchy_rule

```python
add_hierarchy_rule(resource_type: str, permission: str, implies: str)
```

Add a single hierarchy rule (for complex/branching hierarchies).

**Parameters:**
- `resource_type`: The resource type
- `permission`: The higher permission
- `implies`: The permission it implies

**Example:**
```python
authz.add_hierarchy_rule("doc", "admin", "read")
authz.add_hierarchy_rule("doc", "admin", "share")
```

*Source: sdk/src/postkit/authz/client.py:502*

---

### bulk_grant

```python
bulk_grant(permission: str, *, resource: Entity, subject_ids: list[str]) -> int
```

Grant permission to many users at once (single statement).

**Example:**
```python
authz.bulk_grant("read", resource=("doc", "1"), subject_ids=["alice", "bob", "carol"])
```

*Source: sdk/src/postkit/authz/client.py:674*

---

### bulk_grant_resources

```python
bulk_grant_resources(permission: str, *, resource_type: str, resource_ids: list[str], subject: Entity, subject_relation: str | None = None) -> int
```

Grant permission to a subject on many resources at once.

**Example:**
```python
authz.bulk_grant_resources(
    "read",
    resource_type="doc",
    resource_ids=["doc-1", "doc-2", "doc-3"],
    subject=("team", "engineering"),
)
```

*Source: sdk/src/postkit/authz/client.py:692*

---

### check

```python
check(user_id: str, permission: str, resource: Entity) -> bool
```

Check if a user has a permission on a resource.

**Parameters:**
- `user_id`: The user ID
- `permission`: The permission to check (e.g., "read", "write")
- `resource`: The resource as (type, id) tuple

**Returns:** True if the user has the permission

**Example:**
```python
if authz.check("alice", "read", ("repo", "api")):
    return repo_contents
```

*Source: sdk/src/postkit/authz/client.py:201*

---

### check_all

```python
check_all(user_id: str, permissions: list[str], resource: Entity) -> bool
```

Check if a user has all of the specified permissions.

**Parameters:**
- `user_id`: The user ID
- `permissions`: List of permissions (user needs all of them)
- `resource`: The resource as (type, id) tuple

**Returns:** True if the user has all of the permissions

*Source: sdk/src/postkit/authz/client.py:246*

---

### check_any

```python
check_any(user_id: str, permissions: list[str], resource: Entity) -> bool
```

Check if a user has any of the specified permissions.

**Parameters:**
- `user_id`: The user ID
- `permissions`: List of permissions (user needs at least one)
- `resource`: The resource as (type, id) tuple

**Returns:** True if the user has at least one of the permissions

*Source: sdk/src/postkit/authz/client.py:225*

---

### check_subject

```python
check_subject(subject_type: str, subject_id: str, permission: str, resource: Entity) -> bool
```

Check if a subject has a permission on a resource.

**Parameters:**
- `subject_type`: The subject type (e.g., "api_key", "service")
- `subject_id`: The subject ID
- `permission`: The permission to check (e.g., "read", "write")
- `resource`: The resource as (type, id) tuple

**Returns:** True if the subject has the permission

**Example:**
```python
# Check if an API key has read permission
if authz.check_subject("api_key", key_id, "read", ("repo", "api")):
    return repo_contents

# Check if a service can write to a resource
if authz.check_subject("service", "billing", "write", ("customer", "cust-1")):
    update_customer()
```

*Source: sdk/src/postkit/authz/client.py:266*

---

### check_subject_all

```python
check_subject_all(subject_type: str, subject_id: str, permissions: list[str], resource: Entity) -> bool
```

Check if a subject has all of the specified permissions.

**Parameters:**
- `subject_type`: The subject type (e.g., "api_key", "service")
- `subject_id`: The subject ID
- `permissions`: List of permissions (subject needs all of them)
- `resource`: The resource as (type, id) tuple

**Returns:** True if the subject has all of the permissions

*Source: sdk/src/postkit/authz/client.py:343*

---

### check_subject_any

```python
check_subject_any(subject_type: str, subject_id: str, permissions: list[str], resource: Entity) -> bool
```

Check if a subject has any of the specified permissions.

**Parameters:**
- `subject_type`: The subject type (e.g., "api_key", "service")
- `subject_id`: The subject ID
- `permissions`: List of permissions (subject needs at least one)
- `resource`: The resource as (type, id) tuple

**Returns:** True if the subject has at least one of the permissions

*Source: sdk/src/postkit/authz/client.py:311*

---

### cleanup_expired

```python
cleanup_expired() -> dict
```

Remove expired grants.

**Returns:** Dictionary with count of deleted tuples

**Example:**
```python
result = authz.cleanup_expired()
print(f"Removed {result['tuples_deleted']} expired grants")
```

*Source: sdk/src/postkit/authz/client.py:762*

---

### clear_actor

```python
clear_actor() -> None
```

Clear actor context.

*Source: sdk/src/postkit/base.py:328*

---

### clear_expiration

```python
clear_expiration(permission: str, *, resource: Entity, subject: Entity) -> bool
```

Remove expiration from a grant (make it permanent).

**Parameters:**
- `permission`: The permission/relation
- `resource`: The resource as (type, id) tuple
- `subject`: The subject as (type, id) tuple

**Returns:** True if grant was found and updated

**Example:**
```python
authz.clear_expiration("read", resource=("doc", "1"), subject=("user", "alice"))
```

*Source: sdk/src/postkit/authz/client.py:823*

---

### clear_hierarchy

```python
clear_hierarchy(resource_type: str) -> int
```

Clear all hierarchy rules for a resource type.

*Source: sdk/src/postkit/authz/client.py:529*

---

### explain

```python
explain(user_id: str, permission: str, resource: Entity) -> list[str]
```

Explain why a user has a permission.

**Parameters:**
- `user_id`: The user ID
- `permission`: The permission to explain
- `resource`: The resource as (type, id) tuple

**Returns:** List of human-readable explanation strings

**Example:**
```python
paths = authz.explain("alice", "read", ("repo", "api"))
# ["HIERARCHY: alice is member of team:eng which has admin (admin -> read)"]
```

*Source: sdk/src/postkit/authz/client.py:375*

---

### extend_expiration

```python
extend_expiration(permission: str, *, resource: Entity, subject: Entity, extension: timedelta) -> datetime
```

Extend an existing expiration by a given interval.

**Parameters:**
- `permission`: The permission/relation
- `resource`: The resource as (type, id) tuple
- `subject`: The subject as (type, id) tuple
- `extension`: Time to add to current expiration

**Returns:** The new expiration time

**Example:**
```python
new_expires = authz.extend_expiration("read", resource=("doc", "1"),
                                      subject=("user", "alice"),
                                      extension=timedelta(days=30))
```

*Source: sdk/src/postkit/authz/client.py:859*

---

### filter_authorized

```python
filter_authorized(user_id: str, resource_type: str, permission: str, resource_ids: list[str]) -> list[str]
```

Filter resource IDs to only those the user can access.

*Source: sdk/src/postkit/authz/client.py:475*

---

### get_audit_events

```python
get_audit_events(*, limit: int = 100, event_type: str | None = None, actor_id: str | None = None, resource: Entity | None = None, subject: Entity | None = None) -> list[dict]
```

Query audit events with optional filters.

**Parameters:**
- `limit`: Maximum number of events to return (default 100)
- `event_type`: Filter by event type (e.g., 'tuple_created')
- `actor_id`: Filter by actor ID
- `resource`: Filter by resource as (type, id) tuple
- `subject`: Filter by subject as (type, id) tuple

**Returns:** List of audit event dictionaries

**Example:**
```python
events = authz.get_audit_events(actor_id="admin@acme.com", limit=50)
for event in events:
    print(f"{event['event_type']}: {event['resource']}")
```

*Source: sdk/src/postkit/authz/client.py:546*

---

### get_stats

```python
get_stats() -> dict
```

Get namespace statistics for monitoring.

**Returns:** Dictionary with:
- tuple_count: Number of relationship tuples
- hierarchy_rule_count: Number of hierarchy rules
- unique_users: Distinct users with permissions
- unique_resources: Distinct resources with permissions

**Example:**
```python
stats = authz.get_stats()
print(f"Tuples: {stats['tuple_count']}, Users: {stats['unique_users']}")
```

*Source: sdk/src/postkit/authz/client.py:651*

---

### grant

```python
grant(permission: str, *, resource: Entity, subject: Entity, subject_relation: str | None = None, expires_at: datetime | None = None) -> int
```

Grant a permission on a resource to a subject.

**Parameters:**
- `permission`: The permission to grant (e.g., "admin", "read")
- `resource`: The resource as (type, id) tuple (e.g., ("repo", "api"))
- `subject`: The subject as (type, id) tuple (e.g., ("team", "eng"))
- `subject_relation`: Optional relation on the subject (e.g., "admin" for team#admin)
- `expires_at`: Optional expiration time for time-bound permissions

**Returns:** The tuple ID

**Example:**
```python
authz.grant("admin", resource=("repo", "api"), subject=("team", "eng"))
authz.grant("read", resource=("repo", "api"), subject=("user", "alice"))
# Grant only to team admins:
authz.grant("write", resource=("repo", "api"), subject=("team", "eng"), subject_relation="admin")
# Grant with expiration:
authz.grant("read", resource=("doc", "1"), subject=("user", "bob"),
           expires_at=datetime.now(timezone.utc) + timedelta(days=30))
```

*Source: sdk/src/postkit/authz/client.py:80*

---

### list_expiring

```python
list_expiring(within: timedelta = datetime.timedelta(days=7)) -> list[dict]
```

List grants expiring within the given timeframe.

**Parameters:**
- `within`: Time window to check (default 7 days).

**Returns:** List of grants with their expiration times

**Example:**
```python
expiring = authz.list_expiring(within=timedelta(days=30))
for grant in expiring:
    print(f"{grant['subject']} access to {grant['resource']} expires {grant['expires_at']}")
```

*Source: sdk/src/postkit/authz/client.py:732*

---

### list_resources

```python
list_resources(user_id: str, resource_type: str, permission: str, *, limit: int | None = None, cursor: str | None = None) -> list[str]
```

List resources a user has a permission on.

**Parameters:**
- `user_id`: The user ID
- `resource_type`: The resource type to list
- `permission`: The permission to check
- `limit`: Maximum number of results (optional)
- `cursor`: Pagination cursor (optional)

**Returns:** List of resource IDs

**Example:**
```python
repos = authz.list_resources("alice", "repo", "read")
# ["api", "frontend", "docs"]
```

*Source: sdk/src/postkit/authz/client.py:437*

---

### list_users

```python
list_users(permission: str, resource: Entity, *, limit: int | None = None, cursor: str | None = None) -> list[str]
```

List users who have a permission on a resource.

**Parameters:**
- `permission`: The permission to check
- `resource`: The resource as (type, id) tuple
- `limit`: Maximum number of results (optional)
- `cursor`: Pagination cursor (optional)

**Returns:** List of user IDs

**Example:**
```python
users = authz.list_users("read", ("repo", "api"))
# ["alice", "bob", "charlie"]
```

*Source: sdk/src/postkit/authz/client.py:400*

---

### remove_hierarchy_rule

```python
remove_hierarchy_rule(resource_type: str, permission: str, implies: str)
```

Remove a single hierarchy rule.

*Source: sdk/src/postkit/authz/client.py:521*

---

### revoke

```python
revoke(permission: str, *, resource: Entity, subject: Entity, subject_relation: str | None = None) -> bool
```

Revoke a permission on a resource from a subject.

**Parameters:**
- `permission`: The permission to revoke
- `resource`: The resource as (type, id) tuple
- `subject`: The subject as (type, id) tuple
- `subject_relation`: Optional relation on the subject (e.g., "admin" for team#admin)

**Returns:** True if a tuple was deleted

**Example:**
```python
authz.revoke("read", resource=("repo", "api"), subject=("user", "alice"))
# Revoke from team admins only:
authz.revoke("write", resource=("repo", "api"), subject=("team", "eng"), subject_relation="admin")
```

*Source: sdk/src/postkit/authz/client.py:144*

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

*Source: sdk/src/postkit/base.py:299*

---

### set_expiration

```python
set_expiration(permission: str, *, resource: Entity, subject: Entity, expires_at: datetime | None) -> bool
```

Set or update expiration on an existing grant.

**Parameters:**
- `permission`: The permission/relation
- `resource`: The resource as (type, id) tuple
- `subject`: The subject as (type, id) tuple
- `expires_at`: New expiration time (None to make permanent)

**Returns:** True if grant was found and updated

**Example:**
```python
authz.set_expiration("read", resource=("doc", "1"), subject=("user", "alice"),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30))
```

*Source: sdk/src/postkit/authz/client.py:783*

---

### set_hierarchy

```python
set_hierarchy(resource_type: str, *permissions: str)
```

Define permission hierarchy for a resource type.

**Parameters:**
- `resource_type`: The resource type (e.g., "repo") *permissions: Permissions in order of power (e.g., "admin", "write", "read")

**Example:**
```python
authz.set_hierarchy("repo", "admin", "write", "read")
# Now admin implies write, write implies read
```

*Source: sdk/src/postkit/authz/client.py:485*

---

### verify

```python
verify() -> list[dict]
```

Check for data integrity issues (e.g., group membership cycles).

**Example:**
```python
issues = authz.verify()
for issue in issues:
    print(f"{issue['status']}: {issue['details']}")
```

*Source: sdk/src/postkit/authz/client.py:635*

---
