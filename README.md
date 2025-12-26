# pg-authz

Relationship-Based Access Control (ReBAC) that runs inside your Postgres. No external services.

```sql
SELECT authz.check('alice', 'read', 'document', 'doc-123');  -- true/false
```

## What is this?

Authorization answers "can user X do Y to resource Z?" This library stores and evaluates
relationships — users belong to teams, teams have permissions on resources, resources contain
other resources. Permissions flow through these relationships.

**Good fit:** SaaS apps, internal tools, document systems — anywhere you need "users and teams
with permissions on things."

**Not a fit:** Attribute-based rules (location, time, IP), AWS IAM-style policies, or simple
role-only systems where users just need roles without resource-level grants.

## Features

- Nested teams (groups can contain groups)
- Permission hierarchies (admin → write → read)
- Resource hierarchies (folders contain docs)
- Multi-tenant with row-level security
- Time-bound permissions with expiration
- Audit logging

## Install

```bash
psql $DATABASE_URL -f https://raw.githubusercontent.com/varunchopra/pg-authz/main/dist/pg-authz.sql
```

## Quick Start

```sql
-- Permission hierarchy: admin -> write -> read
SELECT authz.add_hierarchy('repo', 'admin', 'write');
SELECT authz.add_hierarchy('repo', 'write', 'read');

-- Create a team
SELECT authz.write('team', 'engineering', 'member', 'user', 'alice');
SELECT authz.write('team', 'engineering', 'member', 'user', 'bob');

-- Grant the team admin access
SELECT authz.write('repo', 'acme/api', 'admin', 'team', 'engineering');

-- Check permissions
SELECT authz.check('alice', 'read', 'repo', 'acme/api');   -- true (admin implies read)
SELECT authz.check('alice', 'admin', 'repo', 'acme/api');  -- true (via team)
SELECT authz.check('charlie', 'read', 'repo', 'acme/api'); -- false (not on team)
```

## API

```sql
-- Grant/revoke
authz.write(resource_type, resource_id, relation, subject_type, subject_id)
authz.delete(resource_type, resource_id, relation, subject_type, subject_id)

-- Check
authz.check(user_id, permission, resource_type, resource_id)
authz.check_any(user_id, permissions[], resource_type, resource_id)
authz.check_all(user_id, permissions[], resource_type, resource_id)

-- List
authz.list_resources(user_id, resource_type, permission)
authz.list_users(resource_type, resource_id, permission)
authz.filter_authorized(user_id, resource_type, permission, resource_ids[])

-- Hierarchy
authz.add_hierarchy(resource_type, permission, implies)
authz.remove_hierarchy(resource_type, permission, implies)

-- Debug
authz.explain_text(user_id, permission, resource_type, resource_id)
```

## Nested Teams

```sql
SELECT authz.write('team', 'infrastructure', 'member', 'user', 'alice');
SELECT authz.write('team', 'platform', 'member', 'team', 'infrastructure');
SELECT authz.write('team', 'engineering', 'member', 'team', 'platform');

SELECT authz.write('repo', 'api', 'read', 'team', 'engineering');
SELECT authz.check('alice', 'read', 'repo', 'api');  -- true (via nested teams)
```

## Resource Hierarchies

```sql
SELECT authz.write('doc', 'spec', 'parent', 'folder', 'projects');
SELECT authz.write('folder', 'projects', 'parent', 'folder', 'root');
SELECT authz.write('folder', 'root', 'read', 'user', 'alice');

SELECT authz.check('alice', 'read', 'doc', 'spec');  -- true (inherited from folder)
```

## Time-Bound Permissions

```sql
SELECT authz.write('repo', 'api', 'read', 'user', 'contractor', NULL, 'default',
                   now() + interval '30 days');

SELECT * FROM authz.list_expiring('7 days');
SELECT authz.cleanup_expired();  -- run via cron
```

## Multi-Tenancy

```sql
SELECT authz.write('doc', '1', 'read', 'user', 'alice', NULL, 'tenant-acme');
SELECT authz.check('alice', 'read', 'doc', '1', 'tenant-acme');  -- true
SELECT authz.check('alice', 'read', 'doc', '1', 'tenant-other'); -- false

SELECT authz.set_tenant('acme');  -- RLS enforces isolation for non-superusers
```

## Audit Logging

```sql
SELECT authz.set_actor('admin@acme.com', 'req-123', 'Quarterly review');
-- do stuff...
SELECT * FROM authz.audit_events ORDER BY event_time DESC LIMIT 100;
```

## Why No SDK?

Teams build their own data access layers with specific drivers (`asyncpg`, `psycopg`, `pg`, etc.),
connection pooling, and caching. A generic SDK either forces opinions or adds a layer you'll
bypass anyway. Call the SQL directly:

```python
cursor.execute("SELECT authz.check(%s, %s, %s, %s)", (user_id, "read", "doc", doc_id))
```

```typescript
await pool.query("SELECT authz.check($1, $2, $3, $4)", [userId, "read", "doc", docId]);
```

```go
db.QueryRow(ctx, "SELECT authz.check($1, $2, $3, $4)", userID, "read", "doc", docID).Scan(&ok)
```

## Development

```bash
make setup   # Start Postgres in Docker
make test    # Run tests
make clean   # Cleanup
```

## License

Apache 2.0
