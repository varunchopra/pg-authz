# Building an Admin UI

All authorization data lives in Postgres. Use any language or framework you prefer.

## Data Format

### Tuples

The `authz.tuples` table stores permissions as separate columns:

```
resource_type | resource_id | relation | subject_type | subject_id | subject_relation
```

A common way to display this is:

```
resource_type:resource_id#relation -> subject_type:subject_id
```

| Display | Meaning |
|---------|---------|
| `repo:acme-api#owner -> user:alice` | Alice owns acme-api |
| `team:eng#member -> user:bob` | Bob is a member of the eng team |
| `repo:acme-api#read -> team:eng#member` | Members of the eng team can read acme-api |

When `subject_relation` is set (like `member` in the last example), it refers to anyone with that
relation to the subject, not the subject entity itself.

### Hierarchy

The `authz.permission_hierarchy` table stores permission inheritance:

```
resource_type | permission | implies
```

Rows like `(repo, owner, admin)` and `(repo, admin, write)` form a chain:

```
repo: owner -> admin -> write -> read
```

This means an owner automatically has admin, admin has write, and write has read.

## Use Cases

### Customer Support: "Why can't I access this?"

When a user reports they can't access a resource:

```sql
SELECT authz.check('user-123', 'read', 'document', 'doc-456', 'default');
-- Returns: true or false

SELECT authz.explain_text('user-123', 'read', 'document', 'doc-456', 'default');
-- Returns: 'ALLOWED: user-123 -> member of team:eng -> read on document:doc-456'
--      or: 'DENIED: no path found from user-123 to read on document:doc-456'
```

### Debugging: "Who can access this resource?"

Before making a resource public or investigating a potential leak:

```sql
SELECT * FROM authz.list_users('document', 'doc-456', 'read', 'default', 100);
```

Returns:

| user_id |
|---------|
| alice   |
| bob     |
| charlie |

### Onboarding: "What can this user access?"

Review a new employee's permissions or audit an existing user:

```sql
SELECT * FROM authz.list_resources('user-123', 'document', 'read', 'default', 100);
```

Returns:

| resource_type | resource_id |
|---------------|-------------|
| document      | doc-123     |
| document      | doc-456     |

### Compliance: "When was access revoked?"

Prove that access was removed at a specific time:

```sql
SELECT event_time, actor_id, event_type, resource_type, resource_id, subject_id
FROM authz.audit_events
WHERE namespace = 'default'
  AND subject_id = 'user-123'
  AND resource_id = 'doc-456'
  AND event_type = 'tuple_deleted'
ORDER BY event_time DESC;
```

Returns:

| event_time          | actor_id  | event_type    | resource_type | resource_id | subject_id |
|---------------------|-----------|---------------|---------------|-------------|------------|
| 2024-01-15 14:32:00 | admin-789 | tuple_deleted | document      | doc-456     | user-123   |

### Incident Response: "What did this admin change?"

Investigate what permissions someone modified:

```sql
SELECT event_time, event_type, resource_type, resource_id, relation, subject_id
FROM authz.audit_events
WHERE namespace = 'default'
  AND actor_id = 'admin-789'
ORDER BY event_time DESC
LIMIT 50;
```

Returns:

| event_time          | event_type    | resource_type | resource_id | relation | subject_id |
|---------------------|---------------|---------------|-------------|----------|------------|
| 2024-01-15 14:32:00 | tuple_deleted | document      | doc-456     | read     | user-123   |
| 2024-01-15 14:30:00 | tuple_created | document      | doc-789     | write    | user-456   |

### Cleanup: "What grants exist on this resource?"

Before deleting a resource, review all its grants:

```sql
SELECT relation, subject_type, subject_id
FROM authz.tuples
WHERE namespace = 'default'
  AND resource_type = 'document'
  AND resource_id = 'doc-456';
```

Returns:

| relation | subject_type | subject_id  |
|----------|--------------|-------------|
| owner    | user         | alice       |
| read     | team         | engineering |

## Reference

| Table | Purpose |
|-------|---------|
| `authz.tuples` | All permission grants |
| `authz.permission_hierarchy` | Permission inheritance rules |
| `authz.audit_events` | Change history with timestamps and actors |
