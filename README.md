# postkit

Postgres-native identity and configuration. Auth, permissions, and versioned config — no external services.

## Modules

| Module | Schema | Purpose |
|--------|--------|---------|
| [authz](authz/) | `authz` | Authorization (ReBAC permissions) |
| [authn](authn/) | `authn` | Authentication (users, sessions, tokens) |
| [config](config/) | `config` | Versioned configuration (prompts, flags, secrets) |

Each module is independent -- use what you need.

## Install

Requires PostgreSQL 14+.

```bash
git clone https://github.com/varunchopra/postkit.git
cd postkit
make build

# Install everything
psql $DATABASE_URL -f dist/postkit.sql

# Or individual modules
psql $DATABASE_URL -f dist/authz.sql
psql $DATABASE_URL -f dist/authn.sql
psql $DATABASE_URL -f dist/config.sql
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

Optional typed client (requires Python 3.10+):

```bash
pip install git+https://github.com/varunchopra/postkit.git#subdirectory=sdk
```

```python
# Grant alice the admin role on repo:api.
>>> authz.grant("admin", resource=("repo", "api"), subject=("user", "alice"))
1

>>> authz.check("alice", "admin", ("repo", "api"))
True

# Without a hierarchy, admin does not imply read.
>>> authz.check("alice", "read", ("repo", "api"))
False

# Define a permission hierarchy: admin > write > read.
>>> authz.set_hierarchy("repo", "admin", "write", "read")

# Now alice has read access via admin.
>>> authz.check("alice", "read", ("repo", "api"))
True

# Create a versioned config entry.
>>> config.set(
...     "prompts/support-bot",
...     {"template": "You are...", "model": {"name": "claude-sonnet", "temperature": 0.7}},
... )
1

# Deep merge updates into the existing config, creating a new version.
>>> config.merge("prompts/support-bot", {"model": {"temperature": 0.8}})
2

# Read a nested value.
>>> config.get_path("prompts/support-bot", "model", "temperature")
0.8
```

See [sdk/](sdk/) for details.

## Documentation

See [docs/](docs/) for full API reference with function signatures, parameters, and examples.

## Development

```bash
make setup   # Start Postgres in Docker
make build   # Build dist/postkit.sql, dist/authz.sql, dist/authn.sql, dist/config.sql
make test    # Run tests
make docs    # Generate API documentation
make clean   # Cleanup
```

## Working with Agents

We've structured the docs and SDK so you can point an agent like Claude Code at [AGENTS.md](AGENTS.md) in this repo and it'll figure out how to set up identity for your app.

_Or_ you can try out [this Claude Code skill](SKILL.md) in your project.

## License

Apache 2.0
