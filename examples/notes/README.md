# Notes

A multi-tenant notes application demonstrating how to build secure, production-ready SaaS features using postkit's PostgreSQL-native modules.

## Features

- **Multi-tenant organizations** with isolated permissions and data
- **Fine-grained sharing** - share notes with users or teams at view/edit/owner levels
- **Permission hierarchies** - owner automatically implies edit, edit implies view
- **API keys with scoped access** - grant keys access to all notes or specific ones
- **Usage metering** - track seats per org and storage per user
- **Audit trails** - all permission changes logged with actor context
- **Session management** - view and revoke sessions across devices

## Architecture

The app uses a multi-namespace architecture for tenant isolation:

- **Global authn namespace** - User identity (accounts, sessions, API keys) is global
- **Per-org namespaces** - Each organization gets isolated authz, config, and metering namespaces (`org:{org_id}`)
- **Request context** - IP address, user agent, and request ID attached to all operations for audit trails

## Quick Start

```bash
docker compose up --build
```

Open http://localhost:5001

## Demo Walkthrough

1. **Sign up** and create an organization
2. **Create a note** - storage usage is tracked automatically
3. **Share the note** with another user (create a second account first)
4. **View audit log** in Organization Settings → Audit
5. **Check usage** in Organization Settings → Usage
6. **Create an API key** with scoped permissions in Dashboard → API Keys

## Project Structure

```
app/
├── __init__.py          # App factory, plan seeding, request middleware
├── auth.py              # Authentication helpers, decorators, API key scopes
├── db.py                # Database clients (authn, authz, config, meter)
├── config.py            # Environment configuration
├── schemas.py           # Pydantic request validation
├── routes/
│   ├── api/             # RESTful API endpoints
│   │   ├── notes.py     # Note CRUD with permission checks
│   │   ├── users.py     # User auth endpoints
│   │   └── api_keys.py  # API key management
│   └── views/           # HTML form routes
│       ├── auth.py      # Login, signup, password reset
│       ├── notes.py     # Note UI with sharing
│       ├── orgs.py      # Org settings, members, audit
│       └── teams.py     # Team management
└── templates/           # Jinja2 templates
```

## postkit Modules Used

| Module | Purpose |
|--------|---------|
| **authn** | User accounts, sessions, API keys, password reset |
| **authz** | Fine-grained permissions, hierarchies, team sharing |
| **config** | Plan definitions (Free/Pro/Enterprise), org settings |
| **meter** | Seat allocation per org, storage tracking per user |
