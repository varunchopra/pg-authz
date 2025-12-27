# authz

Relationship-Based Access Control (ReBAC) for PostgreSQL.

## Install

```bash
# Using psql with source files
psql $DATABASE_URL -f authz/install.sql

# Or using pre-built distribution
psql $DATABASE_URL -f dist/authz.sql
```

## Quick Start

```sql
-- Permission hierarchy: admin -> write -> read
SELECT authz.add_hierarchy('repo', 'admin', 'write');
SELECT authz.add_hierarchy('repo', 'write', 'read');

-- Create a team
SELECT authz.write('team', 'engineering', 'member', 'user', 'alice');

-- Grant the team admin access
SELECT authz.write('repo', 'acme/api', 'admin', 'team', 'engineering');

-- Check permissions
SELECT authz.check('alice', 'read', 'repo', 'acme/api');  -- true
```

## API Reference

See the main [README](../README.md) for full API documentation.

## Directory Structure

```
authz/
├── install.sql           # Install script for psql
├── src/
│   ├── schema/           # Tables, indexes, types
│   ├── functions/        # SQL functions
│   └── triggers/         # Database triggers
└── tests/                # Python test suite
```

## Development

```bash
# From repository root
make build   # Build dist/authz.sql
make test    # Run tests
```
