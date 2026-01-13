# Notes

Multi-tenant notes app demonstrating postkit modules.

## Quick Start

```bash
docker compose up --build
```

Open http://localhost:5001

## What This Demonstrates

- **Multi-tenant isolation** - per-org namespaces for authz, config, meter
- **Permission hierarchies** - owner > edit > view
- **Fine-grained sharing** - share notes with users or teams
- **Scoped API keys** - grant keys access to all notes or specific ones
- **Usage metering** - seats per org, storage per user
- **Audit trails** - actor context on all operations
- **Session management** - view and revoke across devices

## Project Structure

```
app/
├── auth.py              # Auth helpers, decorators, token handling
├── db.py                # Database clients (authn, authz, config, meter)
├── routes/api/          # REST endpoints
└── routes/views/        # HTML form routes
```

## postkit Modules Used

| Module | Purpose |
|--------|---------|
| **authn** | Accounts, sessions, API keys, password reset |
| **authz** | Permissions, hierarchies, team sharing |
| **config** | Plan definitions, org settings |
| **meter** | Seat allocation, storage tracking |

## Not Included

CSRF protection, rate limiting. See `auth.py` for what is implemented.
