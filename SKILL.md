---
name: postkit
description: PostgreSQL-native identity, configuration, and metering. Use when working with user management, sessions, permissions, access control, login/logout, MFA, password resets, role-based access, versioned configuration, prompts, feature flags, secrets, usage tracking, quotas, or billing periods in PostgreSQL. Covers authn (user/session management), authz (ReBAC permissions), config (versioned key-value storage), and meter (usage tracking with reservations).
---

## Setup (REQUIRED FIRST STEP)

Clone the repository if not already present:

```bash
[ -d postkit ] || git clone https://github.com/varunchopra/postkit.git
```

Then build the dist files:

```bash
cd postkit && make build && cd ..
```

## Instructions

1. Read `postkit/AGENTS.md` first (written specifically for LLMs)
2. Read the relevant module docs based on what the user needs:
   - Authentication (users/sessions): `postkit/docs/authn/`
   - Authorization (permissions): `postkit/docs/authz/`
   - Configuration (prompts, flags, secrets): `postkit/docs/config/`
   - Metering (usage tracking, quotas): `postkit/docs/meter/`
3. Check `sdk.md` and `sql.md` in those directories for function signatures
4. Look at tests for usage examples: `postkit/sdk/tests/`

## Documentation Map

| What you need | Where to look |
|---------------|---------------|
| LLM-specific guidance | `postkit/AGENTS.md` |
| Project overview | `postkit/README.md` |
| authn docs | `postkit/docs/authn/sql.md`, `postkit/docs/authn/sdk.md` |
| authz docs | `postkit/docs/authz/sql.md`, `postkit/docs/authz/sdk.md` |
| config docs | `postkit/docs/config/sql.md`, `postkit/docs/config/sdk.md` |
| meter docs | `postkit/docs/meter/sql.md`, `postkit/docs/meter/sdk.md` |
| SQL source | `postkit/{module}/src/` |
| Python SDK source | `postkit/sdk/src/postkit/` |
| Test examples | `postkit/sdk/tests/` |
| Built SQL files | `postkit/dist/` (after `make build`) |