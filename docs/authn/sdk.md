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

*Source: sdk/src/postkit/authn/client.py:343*

---

### cleanup_expired

```python
cleanup_expired() -> dict
```

Clean up expired sessions, tokens, and old login attempts.

*Source: sdk/src/postkit/authn/client.py:441*

---

### clear_actor

```python
clear_actor() -> None
```

Clear actor context.

*Source: sdk/src/postkit/authn/client.py:478*

---

### clear_attempts

```python
clear_attempts(email: str) -> int
```

Clear login attempts for an email. Returns count deleted.

*Source: sdk/src/postkit/authn/client.py:434*

---

### consume_token

```python
consume_token(token_hash: str, token_type: str) -> dict | None
```

Consume a one-time token.

*Source: sdk/src/postkit/authn/client.py:313*

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

*Source: sdk/src/postkit/authn/client.py:217*

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

*Source: sdk/src/postkit/authn/client.py:288*

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

*Source: sdk/src/postkit/authn/client.py:128*

---

### delete_user

```python
delete_user(user_id: str) -> bool
```

Permanently delete a user and all associated data.

*Source: sdk/src/postkit/authn/client.py:184*

---

### disable_user

```python
disable_user(user_id: str) -> bool
```

Disable user and revoke all their sessions.

*Source: sdk/src/postkit/authn/client.py:170*

---

### enable_user

```python
enable_user(user_id: str) -> bool
```

Re-enable a disabled user.

*Source: sdk/src/postkit/authn/client.py:177*

---

### extend_session

```python
extend_session(token_hash: str, extend_by: timedelta | None = None) -> datetime | None
```

Extend session expiration. Returns new expires_at.

*Source: sdk/src/postkit/authn/client.py:256*

---

### get_audit_events

```python
get_audit_events(limit: int = 100, event_type: str | None = None, resource_type: str | None = None, resource_id: str | None = None) -> list[dict]
```

Query audit events.

*Source: sdk/src/postkit/authn/client.py:485*

---

### get_credentials

```python
get_credentials(email: str) -> dict | None
```

Get credentials for login verification.

*Source: sdk/src/postkit/authn/client.py:198*

---

### get_mfa

```python
get_mfa(user_id: str, mfa_type: str) -> list[dict]
```

Get MFA secrets for verification. Returns secrets!

*Source: sdk/src/postkit/authn/client.py:368*

---

### get_recent_attempts

```python
get_recent_attempts(email: str, limit: int = 10) -> list[dict]
```

Get recent login attempts for an email.

*Source: sdk/src/postkit/authn/client.py:427*

---

### get_stats

```python
get_stats() -> dict
```

Get namespace statistics.

*Source: sdk/src/postkit/authn/client.py:449*

---

### get_user

```python
get_user(user_id: str) -> dict | None
```

Get user by ID. Does not return password_hash.

*Source: sdk/src/postkit/authn/client.py:149*

---

### get_user_by_email

```python
get_user_by_email(email: str) -> dict | None
```

Get user by email. Does not return password_hash.

*Source: sdk/src/postkit/authn/client.py:156*

---

### has_mfa

```python
has_mfa(user_id: str) -> bool
```

Check if user has any MFA method enabled.

*Source: sdk/src/postkit/authn/client.py:396*

---

### invalidate_tokens

```python
invalidate_tokens(user_id: str, token_type: str) -> int
```

Invalidate all unused tokens of a type for a user.

*Source: sdk/src/postkit/authn/client.py:336*

---

### is_locked_out

```python
is_locked_out(email: str, window: timedelta | None = None, max_attempts: int | None = None) -> bool
```

Check if an email is locked out due to too many failed attempts.

*Source: sdk/src/postkit/authn/client.py:415*

---

### list_mfa

```python
list_mfa(user_id: str) -> list[dict]
```

List MFA methods. Does NOT return secrets.

*Source: sdk/src/postkit/authn/client.py:375*

---

### list_sessions

```python
list_sessions(user_id: str) -> list[dict]
```

List active sessions for a user. Does not return token_hash.

*Source: sdk/src/postkit/authn/client.py:281*

---

### list_users

```python
list_users(limit: int = 100, cursor: str | None = None) -> list[dict]
```

List users with pagination.

*Source: sdk/src/postkit/authn/client.py:191*

---

### record_login_attempt

```python
record_login_attempt(email: str, success: bool, ip_address: str | None = None) -> None
```

Record a login attempt.

*Source: sdk/src/postkit/authn/client.py:403*

---

### record_mfa_use

```python
record_mfa_use(mfa_id: str) -> bool
```

Record that an MFA method was used.

*Source: sdk/src/postkit/authn/client.py:389*

---

### remove_mfa

```python
remove_mfa(mfa_id: str) -> bool
```

Remove an MFA method.

*Source: sdk/src/postkit/authn/client.py:382*

---

### revoke_all_sessions

```python
revoke_all_sessions(user_id: str) -> int
```

Revoke all sessions for a user. Returns count revoked.

*Source: sdk/src/postkit/authn/client.py:274*

---

### revoke_session

```python
revoke_session(token_hash: str) -> bool
```

Revoke a session.

*Source: sdk/src/postkit/authn/client.py:267*

---

### set_actor

```python
set_actor(actor_id: str, request_id: str | None = None, ip_address: str | None = None, user_agent: str | None = None) -> None
```

Set actor context for audit logging.

*Source: sdk/src/postkit/authn/client.py:457*

---

### update_email

```python
update_email(user_id: str, new_email: str) -> bool
```

Update user's email. Clears email_verified_at.

*Source: sdk/src/postkit/authn/client.py:163*

---

### update_password

```python
update_password(user_id: str, new_password_hash: str) -> bool
```

Update user's password hash.

*Source: sdk/src/postkit/authn/client.py:210*

---

### validate_session

```python
validate_session(token_hash: str) -> dict | None
```

Validate a session token.

*Source: sdk/src/postkit/authn/client.py:244*

---

### verify_email

```python
verify_email(token_hash: str) -> dict | None
```

Verify email using a token.

*Source: sdk/src/postkit/authn/client.py:325*

---
