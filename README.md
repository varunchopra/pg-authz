# postkit

Postgres-native authentication, authorization, and organization management. No external services.

**For LLMs**: See [AGENTS.md](AGENTS.md).

```sql
SELECT authz.check('alice', 'read', 'document', 'doc-123');  -- true/false
```

## Modules

| Module | Schema | Purpose |
|--------|--------|---------|
| [authz](authz/) | `authz` | Authorization (ReBAC permissions) |
| [authn](authn/) | `authn` | Authentication (users, sessions, tokens) |

Each module is independent - use what you need.

## Install

```bash
# Install everything
psql $DATABASE_URL -f https://raw.githubusercontent.com/varunchopra/postkit/main/dist/postkit.sql

# Or individual modules
psql $DATABASE_URL -f https://raw.githubusercontent.com/varunchopra/postkit/main/dist/authz.sql
psql $DATABASE_URL -f https://raw.githubusercontent.com/varunchopra/postkit/main/dist/authn.sql
```

## Why SQL?

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

## Python SDK

For Python projects, there's an optional SDK with a typed client:

```bash
pip install git+https://github.com/varunchopra/postkit.git#subdirectory=sdk
```

```python
from postkit.authz import AuthzClient
from postkit.authn import AuthnClient

authz = AuthzClient(cursor, namespace="my-app")
authz.grant("admin", resource=("repo", "api"), subject=("user", "alice"))

if authz.check("alice", "read", ("repo", "api")):
    print("Access granted")
```

See [sdk/](sdk/) for details.

## Documentation

See [docs/](docs/) for full API reference with function signatures, parameters, and examples.

## Development

```bash
make setup   # Start Postgres in Docker
make build   # Build dist/postkit.sql, dist/authz.sql, dist/authn.sql
make test    # Run tests
make docs    # Generate API documentation
make clean   # Cleanup
```

## License

Apache 2.0
