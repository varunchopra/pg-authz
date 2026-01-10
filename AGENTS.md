# postkit - Agent Guide

PostgreSQL-native identity, configuration, and metering. Auth, permissions, versioned config, and usage tracking - no external services.

## Browsing Documentation

Start at [docs/README.md](docs/README.md), then navigate to module docs:

```
docs/
  README.md              # Start here - links to modules
  {module}/
    README.md            # Module overview + function index
    sdk.md               # Python SDK reference
    sql.md               # SQL function reference
```

For a specific task, read the module README first (has function index with deep links), then the relevant sdk.md or sql.md.

## Key Files

```
{module}/src/functions/    # SQL functions
sdk/src/postkit/
  {module}/client.py       # Python SDK client
sdk/tests/                 # Test examples
dist/
  postkit.sql              # Combined SQL schema (built)
  {module}.sql             # Individual module SQL
```

## Documentation Maintenance

API docs are auto-generated. After modifying code, regenerate:

```bash
make docs
```

This extracts docstrings from Python SDK and `@function` tags from SQL files.

For SQL functions, add documentation tags:
```sql
-- @group Permission Checks

-- @function authz.check
-- @brief Check if a subject has a permission on a resource
-- @param p_subject_type The subject type (e.g., 'user', 'api_key')
-- @param p_subject_id The subject ID
-- @returns True if subject has permission
-- @example SELECT authz.check('user', 'alice', 'read', 'doc', '1');
CREATE OR REPLACE FUNCTION authz.check(...)
```
