# postkit

Postgres-native authentication and authorization. No external services.

## Modules

| Module | Schema | Purpose |
|--------|--------|---------|
| [authz](authz/) | `authz` | Authorization (ReBAC permissions) |
| [authn](authn/) | `authn` | Authentication (users, sessions, tokens) |

Each module is independent -- use what you need.

## Install

```bash
git clone https://github.com/varunchopra/postkit.git
cd postkit
make build

# Install everything
psql $DATABASE_URL -f dist/postkit.sql

# Or individual modules
psql $DATABASE_URL -f dist/authz.sql
psql $DATABASE_URL -f dist/authn.sql
```

## Usage

Works with any language or driver:

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

Optional typed client for Python:

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

## Working with Agents

We've structured the docs and SDK so you can point an agent like Claude Code at [AGENTS.md](AGENTS.md) in this repo and it'll figure out how to set up identity for your app.

_Or_ you can try out [this Claude Code skill](SKILL.md) in your project.

## License

Apache 2.0
