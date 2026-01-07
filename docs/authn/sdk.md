<!-- AUTO-GENERATED. DO NOT EDIT. Run `make docs` to regenerate. -->

# Authn Python SDK

### add_mfa

```python
add_mfa(user_id: str, mfa_type: str, secret: str, name: str | None = None) -> str
```

Add an MFA method for a user.

**Parameters:**
- `user_id`: User ID
- `mfa_type`: 'totp', 'webauthn', or 'recovery_codes'
- `secret`: The MFA secret (caller stores this securely)
- `name`: Optional friendly name

**Returns:** MFA ID (UUID string)

*Source: sdk/src/postkit/authn/client.py:418*

---

### cleanup_expired

```python
cleanup_expired() -> dict
```

Clean up expired sessions, tokens, and old login attempts.

*Source: sdk/src/postkit/authn/client.py:521*

---

### clear_actor

```python
clear_actor() -> None
```

Clear actor context.

*Source: sdk/src/postkit/authn/client.py:574*

---

### clear_attempts

```python
clear_attempts(email: str) -> int
```

Clear login attempts for an email. Returns count deleted.

*Source: sdk/src/postkit/authn/client.py:513*

---

### consume_token

```python
consume_token(token_hash: str, token_type: str) -> dict | None
```

Consume a one-time token.

*Source: sdk/src/postkit/authn/client.py:385*

---

### create_api_key

```python
create_api_key(user_id: str, key_hash: str, name: str | None = None, expires_in: timedelta | None = None) -> str
```

Create an API key for programmatic access.

**Parameters:**
- `user_id`: User ID (owner of the key)
- `key_hash`: Pre-hashed API key (SHA-256)
- `name`: Optional friendly name ("Production", "CI/CD")
- `expires_in`: Optional expiration duration (None = never expires)

**Returns:** API key ID (UUID string)

*Source: sdk/src/postkit/authn/client.py:295*

---

### create_session

```python
create_session(user_id: str, token_hash: str, expires_in: timedelta | None = None, ip_address: str | None = None, user_agent: str | None = None) -> str
```

Create a new session.

**Parameters:**
- `user_id`: User ID
- `token_hash`: Pre-hashed session token (SHA-256)
- `expires_in`: Session duration (default: 7 days)
- `ip_address`: Client IP
- `user_agent`: Client user agent

**Returns:** Session ID (UUID string)

*Source: sdk/src/postkit/authn/client.py:181*

---

### create_token

```python
create_token(user_id: str, token_hash: str, token_type: str, expires_in: timedelta | None = None) -> str
```

Create a one-time use token.

**Parameters:**
- `user_id`: User ID
- `token_hash`: Pre-hashed token (SHA-256)
- `token_type`: 'password_reset', 'email_verify', or 'magic_link'
- `expires_in`: Token lifetime (defaults vary by type)

**Returns:** Token ID (UUID string)

*Source: sdk/src/postkit/authn/client.py:359*

---

### create_user

```python
create_user(email: str, password_hash: str | None = None) -> str
```

Create a new user.

**Parameters:**
- `email`: User's email address (will be normalized to lowercase)
- `password_hash`: Pre-hashed password (None for SSO-only users)

**Returns:** User ID (UUID string)

*Source: sdk/src/postkit/authn/client.py:86*

---

### delete_user

```python
delete_user(user_id: str) -> bool
```

Permanently delete a user and all associated data.

*Source: sdk/src/postkit/authn/client.py:146*

---

### disable_user

```python
disable_user(user_id: str) -> bool
```

Disable user and revoke all their sessions.

*Source: sdk/src/postkit/authn/client.py:130*

---

### enable_user

```python
enable_user(user_id: str) -> bool
```

Re-enable a disabled user.

*Source: sdk/src/postkit/authn/client.py:138*

---

### extend_session

```python
extend_session(token_hash: str, extend_by: timedelta | None = None) -> datetime | None
```

Extend session expiration.

**Returns:** New expires_at timestamp, or None if session invalid/expired/revoked.

*Source: sdk/src/postkit/authn/client.py:221*

---

### get_audit_events

```python
get_audit_events(limit: int = 100, event_type: str | None = None, resource_type: str | None = None, resource_id: str | None = None) -> list[dict]
```

Query audit events.

**Parameters:**
- `limit`: Maximum number of events to return (default 100)
- `event_type`: Filter by event type (e.g., 'user_created', 'session_revoked')
- `resource_type`: Filter by resource type (e.g., 'user', 'session')
- `resource_id`: Filter by resource ID

**Returns:** List of audit event dictionaries

*Source: sdk/src/postkit/authn/client.py:580*

---

### get_credentials

```python
get_credentials(email: str) -> dict | None
```

Get credentials for login verification.

*Source: sdk/src/postkit/authn/client.py:161*

---

### get_mfa

```python
get_mfa(user_id: str, mfa_type: str) -> list[dict]
```

Get MFA secrets for verification. Returns secrets!

*Source: sdk/src/postkit/authn/client.py:444*

---

### get_recent_attempts

```python
get_recent_attempts(email: str, limit: int = 10) -> list[dict]
```

Get recent login attempts for an email.

*Source: sdk/src/postkit/authn/client.py:506*

---

### get_stats

```python
get_stats() -> dict
```

Get namespace statistics.

*Source: sdk/src/postkit/authn/client.py:532*

---

### get_user

```python
get_user(user_id: str) -> dict | None
```

Get user by ID. Does not return password_hash.

*Source: sdk/src/postkit/authn/client.py:108*

---

### get_user_by_email

```python
get_user_by_email(email: str) -> dict | None
```

Get user by email. Does not return password_hash.

*Source: sdk/src/postkit/authn/client.py:115*

---

### has_mfa

```python
has_mfa(user_id: str) -> bool
```

Check if user has any MFA method enabled.

*Source: sdk/src/postkit/authn/client.py:474*

---

### invalidate_tokens

```python
invalidate_tokens(user_id: str, token_type: str) -> int
```

Invalidate all unused tokens of a type for a user.

*Source: sdk/src/postkit/authn/client.py:410*

---

### is_locked_out

```python
is_locked_out(email: str, window: timedelta | None = None, max_attempts: int | None = None) -> bool
```

Check if an email is locked out due to too many failed attempts.

*Source: sdk/src/postkit/authn/client.py:494*

---

### list_api_keys

```python
list_api_keys(user_id: str) -> list[dict]
```

List active API keys for a user. Does not return key_hash.

*Source: sdk/src/postkit/authn/client.py:352*

---

### list_mfa

```python
list_mfa(user_id: str) -> list[dict]
```

List MFA methods. Does NOT return secrets.

*Source: sdk/src/postkit/authn/client.py:451*

---

### list_sessions

```python
list_sessions(user_id: str) -> list[dict]
```

List active sessions for a user. Does not return token_hash.

*Source: sdk/src/postkit/authn/client.py:288*

---

### list_users

```python
list_users(limit: int = 100, cursor: str | None = None) -> list[dict]
```

List users with pagination.

*Source: sdk/src/postkit/authn/client.py:154*

---

### record_login_attempt

```python
record_login_attempt(email: str, success: bool, ip_address: str | None = None) -> None
```

Record a login attempt.

*Source: sdk/src/postkit/authn/client.py:481*

---

### record_mfa_use

```python
record_mfa_use(mfa_id: str) -> bool
```

Record that an MFA method was used.

*Source: sdk/src/postkit/authn/client.py:466*

---

### remove_mfa

```python
remove_mfa(mfa_id: str) -> bool
```

Remove an MFA method.

*Source: sdk/src/postkit/authn/client.py:458*

---

### revoke_all_api_keys

```python
revoke_all_api_keys(user_id: str) -> int
```

Revoke all API keys for a user. Returns count revoked.

*Source: sdk/src/postkit/authn/client.py:344*

---

### revoke_all_sessions

```python
revoke_all_sessions(user_id: str) -> int
```

Revoke all sessions for a user. Returns count revoked.

*Source: sdk/src/postkit/authn/client.py:260*

---

### revoke_api_key

```python
revoke_api_key(key_id: str) -> bool
```

Revoke an API key.

*Source: sdk/src/postkit/authn/client.py:336*

---

### revoke_other_sessions

```python
revoke_other_sessions(user_id: str, except_session_id: str) -> int
```

Revoke all sessions except the specified one ("sign out other devices").

**Parameters:**
- `user_id`: User whose sessions to revoke
- `except_session_id`: Session ID to preserve (the current session)

**Returns:** Count of sessions revoked (excludes the preserved session)

*Source: sdk/src/postkit/authn/client.py:268*

---

### revoke_session

```python
revoke_session(token_hash: str) -> bool
```

Revoke a session.

*Source: sdk/src/postkit/authn/client.py:237*

---

### revoke_session_by_id

```python
revoke_session_by_id(session_id: str, user_id: str) -> bool
```

Revoke a session by ID (for manage devices UI).

*Source: sdk/src/postkit/authn/client.py:245*

---

### set_actor

```python
set_actor(actor_id: str | None = None, request_id: str | None = None, on_behalf_of: str | None = None, reason: str | None = None, *, ip_address: str | None = None, user_agent: str | None = None) -> None
```

Set actor context for audit logging. Only updates fields that are passed.

**Parameters:**
- `actor_id`: The actor making changes (e.g., 'user:alice')
- `request_id`: Request/correlation ID for tracing
- `on_behalf_of`: Principal being represented
- `reason`: Reason for the action
- `ip_address`: Client IP address
- `user_agent`: Client user agent string

**Example:**
```python
# In before_request: set HTTP context
authn.clear_actor()
authn.set_actor(request_id=req_id, ip_address=ip, user_agent=ua)

# After authentication: add actor_id (preserves HTTP context)
authn.set_actor(actor_id="user:alice")
```

*Source: sdk/src/postkit/authn/client.py:540*

---

### update_email

```python
update_email(user_id: str, new_email: str) -> bool
```

Update user's email. Clears email_verified_at.

*Source: sdk/src/postkit/authn/client.py:122*

---

### update_password

```python
update_password(user_id: str, new_password_hash: str) -> bool
```

Update user's password hash.

*Source: sdk/src/postkit/authn/client.py:173*

---

### validate_api_key

```python
validate_api_key(key_hash: str) -> dict | None
```

Validate an API key.

**Returns:** Dict with user_id, key_id, name, expires_at or None if invalid

*Source: sdk/src/postkit/authn/client.py:321*

---

### validate_session

```python
validate_session(token_hash: str) -> dict | None
```

Validate a session token.

*Source: sdk/src/postkit/authn/client.py:209*

---

### verify_email

```python
verify_email(token_hash: str) -> dict | None
```

Verify email using a token.

*Source: sdk/src/postkit/authn/client.py:398*

---
