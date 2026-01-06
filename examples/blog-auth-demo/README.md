# Auth Demo

Authentication demo with password login, Google SSO, session management, and API keys.

## Structure

```
app/
├── __init__.py        # App factory
├── config.py          # Environment config
├── db.py              # Connection pooling
├── auth.py            # Auth helpers
├── schemas.py         # Pydantic request models
├── routes/
│   ├── api/           # JSON API endpoints (/api/*)
│   │   ├── health.py
│   │   ├── users.py
│   │   ├── sso.py
│   │   └── api_keys.py
│   └── views/         # HTML views (/)
│       ├── auth.py
│       └── dashboard.py
├── templates/         # Jinja2 templates
└── static/css/        # Styles
```

## Quick Start

```bash
docker compose up --build
```

- UI: http://localhost:5001
- API: http://localhost:5001/api

## Configuration

Edit `docker-compose.yml`:

```yaml
environment:
  DATABASE_URL: postgresql://app:app@db/app
  SECRET_KEY: your-random-secret-key
  DEBUG: "true"  # Shows reset token in flash message
  GOOGLE_CLIENT_ID: your-client-id
  GOOGLE_CLIENT_SECRET: your-secret
  GOOGLE_REDIRECT_URI_API: http://localhost:5001/api/auth/google/callback
  GOOGLE_REDIRECT_URI_VIEW: http://localhost:5001/auth/google/callback
```

## API

### Auth Flow

```bash
# Sign up
curl -X POST http://localhost:5001/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "secret123"}'

# Log in → get token
curl -X POST http://localhost:5001/api/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "secret123"}'

# Use token
curl http://localhost:5001/api/me -H "Authorization: Bearer TOKEN"
```

### Password Reset

```bash
# Request reset (shows debug_token if DEBUG=true)
curl -X POST http://localhost:5001/api/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com"}'

# Reset password
curl -X POST http://localhost:5001/api/reset-password \
  -H "Content-Type: application/json" \
  -d '{"token": "RESET_TOKEN", "password": "newpassword123"}'
```

### Sessions

```bash
# List sessions
curl http://localhost:5001/api/sessions -H "Authorization: Bearer TOKEN"

# Revoke all other sessions (returns new token)
curl -X DELETE http://localhost:5001/api/sessions -H "Authorization: Bearer TOKEN"
```

### API Keys

```bash
# Create
curl -X POST http://localhost:5001/api/api-keys \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci"}'

# Use (Api-Key header)
curl http://localhost:5001/api/me -H "Api-Key: KEY"

# List / Revoke
curl http://localhost:5001/api/api-keys -H "Authorization: Bearer TOKEN"
curl -X DELETE http://localhost:5001/api/api-keys/KEY_ID -H "Authorization: Bearer TOKEN"
```

### Google SSO

```bash
curl http://localhost:5001/api/auth/google
# → {"url": "https://accounts.google.com/..."}
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/health | - | Health check |
| POST | /api/signup | - | Create user |
| POST | /api/login | - | Get session token |
| POST | /api/logout | Bearer | Revoke current session |
| GET | /api/me | Bearer/Api-Key | Current user |
| POST | /api/forgot-password | - | Request password reset |
| POST | /api/reset-password | - | Reset with token |
| GET | /api/sessions | Bearer/Api-Key | List sessions |
| DELETE | /api/sessions | Bearer | Revoke all other sessions |
| GET | /api/auth/google | - | Get OAuth URL |
| GET | /api/auth/google/callback | - | OAuth callback |
| POST | /api/api-keys | Bearer/Api-Key | Create API key |
| GET | /api/api-keys | Bearer/Api-Key | List API keys |
| DELETE | /api/api-keys/:id | Bearer/Api-Key | Revoke API key |

## View Routes

| Path | Description |
|------|-------------|
| / | Redirect to /login or /dashboard |
| /login | Login page |
| /signup | Registration page |
| /logout | Logout and redirect |
| /forgot-password | Password reset request |
| /reset-password | Set new password |
| /dashboard | User dashboard |
| /sessions | Session management |
| /api-keys | API key management |
| /auth/google | Start Google OAuth |
| /auth/google/callback | OAuth callback |

## Local Development

```bash
pip install -r requirements.txt
pip install -e "../../sdk[binary]"
psql $DATABASE_URL -f ../../dist/authn.sql

DATABASE_URL="postgresql://localhost/app" flask --app app:create_app run --debug --port 5001
```

## Security Notes

- Passwords hashed with Argon2id
- Constant-time password verification
- OAuth state parameter for CSRF protection
- Session validation on every request
- Login rate limiting by email
- Disabled user check on login/SSO
