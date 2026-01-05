# authz

Relationship-Based Access Control (ReBAC) for PostgreSQL. Answers "can user X do Y to resource Z?"

**Good fit:** SaaS apps, internal tools, document systems - anywhere you need "users and teams with permissions on things."

**Not a fit:** Attribute-based rules (location, time, IP), AWS IAM-style policies, or simple role-only systems where users just need roles without resource-level grants.

## Install

See [installation instructions](../README.md#install) in the main README.

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

See [docs/authz/](../docs/authz/) for full API reference.
