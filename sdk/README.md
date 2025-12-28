# postkit

PostgreSQL-native authentication and authorization SDK.

## Installation

```bash
pip install postkit
```

## Usage

```python
import psycopg
from postkit.authz import AuthzClient
from postkit.authn import AuthnClient

conn = psycopg.connect("postgresql://...")
cursor = conn.cursor()

# Authorization
authz = AuthzClient(cursor, namespace="my-app")
authz.grant("admin", resource=("repo", "api"), subject=("user", "alice"))
if authz.check("alice", "read", ("repo", "api")):
    print("Access granted")

# Authentication
authn = AuthnClient(cursor, namespace="my-app")
user_id = authn.create_user("alice@example.com", password_hash="argon2...")
session_id = authn.create_session(user_id, token_hash="sha256...")
```

## Requirements

- PostgreSQL 14+
- The postkit SQL schema installed in your database

See the [main repository](https://github.com/varunchopra/postkit) for SQL installation instructions.

## Documentation

Docs are generated from docstrings—run `make gendocs` from repo root.

The first line becomes the description in API tables, so keep it short. For non-trivial functions, add `Args`, `Returns`, and `Example`:

```python
def check(self, user_id: str, permission: str, resource: Entity) -> bool:
    """
    Check if a user has a permission on a resource.

    Args:
        user_id: The user ID
        permission: The permission to check
        resource: The resource as (type, id) tuple

    Returns:
        True if the user has the permission

    Example:
        if authz.check("alice", "read", ("repo", "api")):
            return repo_contents
    """
```

One-liners are fine for simple getters like `get_user` or `list_sessions`.
