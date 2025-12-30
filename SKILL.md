---
name: postkit
description: PostgreSQL-native authentication and authorization. Use when working with user management, sessions, permissions, access control, login/logout, MFA, password resets, or role-based access in PostgreSQL. Covers authz (ReBAC permissions) and authn (user/session management).
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
   - Authorization (permissions): `postkit/docs/authz/`
   - Authentication (users/sessions): `postkit/docs/authn/`
3. Check `sdk.md` and `sql.md` in those directories for function signatures
4. Look at tests for usage examples: `postkit/sdk/tests/authz/` and `postkit/sdk/tests/authn/`

## Documentation Map

| What you need | Where to look |
|---------------|---------------|
| LLM-specific guidance | `postkit/AGENTS.md` |
| Project overview | `postkit/README.md` |
| authz docs | `postkit/docs/authz/sql.md`, `postkit/docs/authz/sdk.md` |
| authn docs | `postkit/docs/authn/sql.md`, `postkit/docs/authn/sdk.md` |
| SQL source | `postkit/authz/src/`, `postkit/authn/src/` |
| Python SDK source | `postkit/sdk/src/postkit/` |
| Test examples | `postkit/sdk/tests/` |
| Built SQL files | `postkit/dist/` (after `make build`) |