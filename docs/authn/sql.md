<!-- AUTO-GENERATED. DO NOT EDIT. Run `make docs` to regenerate. -->

# Authn SQL API

## API Keys

### authn.create_api_key

```sql
authn.create_api_key(p_user_id: uuid, p_key_hash: text, p_name: text, p_expires_in: interval, p_namespace: text) -> uuid
```

Create an API key for programmatic access

**Parameters:**
- `p_user_id`: Owner of the key
- `p_key_hash`: SHA-256 hash of the actual key (caller generates, hashes, stores hash)
- `p_name`: Optional friendly name ("Production", "CI/CD")
- `p_expires_in`: Optional expiration interval (NULL = never expires)

**Returns:** API key ID

**Example:**
```sql
SELECT authn.create_api_key(user_id, sha256(key), 'Production', '1 year');
```

*Source: authn/src/functions/025_api_keys.sql:1*

---

### authn.list_api_keys

```sql
authn.list_api_keys(p_user_id: uuid, p_namespace: text) -> table(key_id: uuid, name: text, created_at: timestamptz, expires_at: timestamptz, last_used_at: timestamptz)
```

List API keys for a user (for management UI)

**Parameters:**
- `p_user_id`: The user whose keys to list

**Returns:** Active keys with metadata (no key_hash exposed)

**Example:**
```sql
SELECT * FROM authn.list_api_keys(user_id);
```

*Source: authn/src/functions/025_api_keys.sql:175*

---

### authn.revoke_all_api_keys

```sql
authn.revoke_all_api_keys(p_user_id: uuid, p_namespace: text) -> int4
```

Revoke all API keys for a user

**Parameters:**
- `p_user_id`: The user whose keys to revoke

**Returns:** Count of keys revoked

**Example:**
```sql
SELECT authn.revoke_all_api_keys(user_id); -- Security concern, revoke all
```

*Source: authn/src/functions/025_api_keys.sql:139*

---

### authn.revoke_api_key

```sql
authn.revoke_api_key(p_key_id: uuid, p_namespace: text) -> bool
```

Revoke an API key

**Parameters:**
- `p_key_id`: The key ID to revoke

**Returns:** True if key was revoked, false if not found or already revoked

**Example:**
```sql
SELECT authn.revoke_api_key('key-uuid-here');
```

*Source: authn/src/functions/025_api_keys.sql:100*

---

### authn.validate_api_key

```sql
authn.validate_api_key(p_key_hash: text, p_namespace: text) -> table(user_id: uuid, key_id: uuid, name: text, expires_at: timestamptz)
```

Validate an API key and get owner info (hot path)

**Parameters:**
- `p_key_hash`: SHA-256 hash of the key being validated

**Returns:** user_id, key_id, name, expires_at if valid; empty if invalid/expired/revoked

**Example:**
```sql
SELECT * FROM authn.validate_api_key(sha256(key_from_header));
```

*Source: authn/src/functions/025_api_keys.sql:48*

---

## Audit

### authn.clear_actor

```sql
authn.clear_actor() -> void
```

Clear actor context

**Example:**
```sql
SELECT authn.clear_actor();
```

*Source: authn/src/functions/070_audit.sql:40*

---

### authn.create_audit_partition

```sql
authn.create_audit_partition(p_year: int4, p_month: int4) -> text
```

Create a monthly partition for audit events

**Returns:** Partition name if created, NULL if already exists

**Example:**
```sql
SELECT authn.create_audit_partition(2024, 1); -- January 2024
```

*Source: authn/src/functions/070_audit.sql:56*

---

### authn.drop_audit_partitions

```sql
authn.drop_audit_partitions(p_older_than_months: int4) -> setof text
```

Delete old audit partitions (default: keep 7 years for compliance)

**Parameters:**
- `p_older_than_months`: Delete partitions older than this (default 84 = 7 years)

**Returns:** Names of dropped partitions

**Example:**
```sql
SELECT * FROM authn.drop_audit_partitions(84);
```

*Source: authn/src/functions/070_audit.sql:145*

---

### authn.ensure_audit_partitions

```sql
authn.ensure_audit_partitions(p_months_ahead: int4) -> setof text
```

Create partitions for upcoming months (run monthly via cron)

**Parameters:**
- `p_months_ahead`: How many months ahead to create (default 3)

**Returns:** Names of newly created partitions

**Example:**
```sql
SELECT * FROM authn.ensure_audit_partitions(3);
```

*Source: authn/src/functions/070_audit.sql:112*

---

### authn.set_actor

```sql
authn.set_actor(p_actor_id: text, p_request_id: text, p_ip_address: text, p_user_agent: text, p_on_behalf_of: text, p_reason: text) -> void
```

Tag audit events with who made the change (call before user operations)

**Parameters:**
- `p_actor_id`: The admin or API making changes (for audit trail)
- `p_request_id`: Optional request/ticket ID for traceability
- `p_ip_address`: Optional IP address of the client
- `p_user_agent`: Optional user agent string
- `p_on_behalf_of`: Optional principal being represented (e.g., admin acting as customer)
- `p_reason`: Optional reason/context for the action

**Example:**
```sql
SELECT authn.set_actor('user:admin-bob', on_behalf_of := 'user:customer-alice', reason := 'support_ticket:12345');
```

*Source: authn/src/functions/070_audit.sql:1*

---

## Credentials

### authn.get_credentials

```sql
authn.get_credentials(p_email: text, p_namespace: text) -> table(user_id: uuid, password_hash: text, disabled_at: timestamptz)
```

Get password hash for login verification (only function that returns hash)

**Returns:** user_id, password_hash, disabled_at. Verify hash in your app, check disabled_at, then call create_session if valid.

**Example:**
```sql
SELECT * FROM authn.get_credentials('alice@example.com');
```

*Source: authn/src/functions/011_credentials.sql:1*

---

### authn.update_password

```sql
authn.update_password(p_user_id: uuid, p_new_password_hash: text, p_namespace: text) -> bool
```

Update user's password hash (after password change or reset)

**Parameters:**
- `p_new_password_hash`: Argon2id hash of new password

**Example:**
```sql
SELECT authn.update_password(user_id, '$argon2id$...');
```

*Source: authn/src/functions/011_credentials.sql:34*

---

## Lockout

### authn.clear_attempts

```sql
authn.clear_attempts(p_email: text, p_namespace: text) -> int8
```

Clear login attempts to unlock a user (admin function)

**Returns:** Count of attempts cleared

**Example:**
```sql
SELECT authn.clear_attempts('alice@example.com'); -- Unlock user
```

*Source: authn/src/functions/050_lockout.sql:132*

---

### authn.get_recent_attempts

```sql
authn.get_recent_attempts(p_email: text, p_namespace: text, p_limit: int4) -> table(success: bool, ip_address: inet, attempted_at: timestamptz)
```

Get recent login attempts for admin UI or user security page

**Returns:** success, ip_address, attempted_at

**Example:**
```sql
SELECT * FROM authn.get_recent_attempts('alice@example.com');
```

*Source: authn/src/functions/050_lockout.sql:92*

---

### authn.is_locked_out

```sql
authn.is_locked_out(p_email: text, p_namespace: text, p_window: interval, p_max_attempts: int4) -> bool
```

Check if email is locked out due to too many failed attempts

**Parameters:**
- `p_window`: Time window to count failures (default from config)
- `p_max_attempts`: Max failures before lockout (default from config)

**Returns:** True if locked out. Check before allowing login attempt.

**Example:**
```sql
IF authn.is_locked_out(email) THEN show_lockout_error(); END IF;
```

*Source: authn/src/functions/050_lockout.sql:52*

---

### authn.record_login_attempt

```sql
authn.record_login_attempt(p_email: text, p_success: bool, p_ip_address: inet, p_namespace: text) -> void
```

Record a login attempt (success or failure) for lockout tracking

**Parameters:**
- `p_success`: True for successful login, false for failed

**Example:**
```sql
-- After password verification
SELECT authn.record_login_attempt(email, password_correct, '1.2.3.4');
```

*Source: authn/src/functions/050_lockout.sql:1*

---

## MFA

### authn.add_mfa

```sql
authn.add_mfa(p_user_id: uuid, p_mfa_type: text, p_secret: text, p_name: text, p_namespace: text) -> uuid
```

Add an MFA method (TOTP, WebAuthn, or recovery codes)

**Parameters:**
- `p_mfa_type`: One of: 'totp', 'webauthn', 'recovery_codes'
- `p_secret`: The secret to store (TOTP seed, WebAuthn public key, etc.)
- `p_name`: User-friendly name like "My iPhone" or "Backup codes"

**Returns:** MFA method ID

**Example:**
```sql
SELECT authn.add_mfa(user_id, 'totp', 'JBSWY3DPEHPK3PXP', 'Authenticator');
```

*Source: authn/src/functions/040_mfa.sql:1*

---

### authn.get_mfa

```sql
authn.get_mfa(p_user_id: uuid, p_mfa_type: text, p_namespace: text) -> table(mfa_id: uuid, secret: text, name: text)
```

Get MFA secrets for verification (returns raw secrets)

**Returns:** mfa_id, secret, name. Use to verify TOTP code or WebAuthn assertion.

**Example:**
```sql
SELECT * FROM authn.get_mfa(user_id, 'totp'); -- Verify code against secret
```

*Source: authn/src/functions/040_mfa.sql:42*

---

### authn.has_mfa

```sql
authn.has_mfa(p_user_id: uuid, p_namespace: text) -> bool
```

Check if user has any MFA method configured

**Example:**
```sql
IF authn.has_mfa(user_id) THEN prompt_for_mfa(); END IF;
```

*Source: authn/src/functions/040_mfa.sql:185*

---

### authn.list_mfa

```sql
authn.list_mfa(p_user_id: uuid, p_namespace: text) -> table(mfa_id: uuid, mfa_type: text, name: text, created_at: timestamptz, last_used_at: timestamptz)
```

List user's MFA methods for "manage security" UI (no secrets)

**Example:**
```sql
SELECT * FROM authn.list_mfa(user_id);
```

*Source: authn/src/functions/040_mfa.sql:74*

---

### authn.record_mfa_use

```sql
authn.record_mfa_use(p_mfa_id: uuid, p_namespace: text) -> bool
```

Record successful MFA verification (updates last_used_at)

**Example:**
```sql
-- After verifying TOTP code
SELECT authn.record_mfa_use(mfa_id);
```

*Source: authn/src/functions/040_mfa.sql:152*

---

### authn.remove_mfa

```sql
authn.remove_mfa(p_mfa_id: uuid, p_namespace: text) -> bool
```

Remove an MFA method

**Example:**
```sql
SELECT authn.remove_mfa(mfa_id);
```

*Source: authn/src/functions/040_mfa.sql:107*

---

## Maintenance

### authn.cleanup_expired

```sql
authn.cleanup_expired(p_namespace: text) -> table(sessions_deleted: int8, tokens_deleted: int8, api_keys_deleted: int8, attempts_deleted: int8)
```

Delete expired sessions, tokens, API keys, and old login attempts (run via cron)

**Returns:** sessions_deleted, tokens_deleted, api_keys_deleted, attempts_deleted

**Example:**
```sql
-- Add to daily cron job
SELECT * FROM authn.cleanup_expired('default');
```

*Source: authn/src/functions/060_maintenance.sql:1*

---

### authn.get_stats

```sql
authn.get_stats(p_namespace: text) -> table(user_count: int8, verified_user_count: int8, disabled_user_count: int8, active_session_count: int8, active_api_key_count: int8, mfa_enabled_user_count: int8)
```

Get namespace statistics for monitoring dashboards

**Returns:** user_count, verified_user_count, disabled_user_count, active_session_count, active_api_key_count, mfa_enabled_user_count

**Example:**
```sql
SELECT * FROM authn.get_stats('default');
```

*Source: authn/src/functions/060_maintenance.sql:55*

---

## Multi-tenancy

### authn.clear_tenant

```sql
authn.clear_tenant() -> void
```

Clear tenant context. Queries return no rows (fail-closed for safety).

**Example:**
```sql
SELECT authn.clear_tenant();
```

*Source: authn/src/functions/080_rls.sql:17*

---

### authn.set_tenant

```sql
authn.set_tenant(p_tenant_id: text) -> void
```

Set the tenant context for Row-Level Security

**Parameters:**
- `p_tenant_id`: Tenant/organization ID. All queries will be filtered to this tenant.

**Example:**
```sql
-- At start of request, set tenant from JWT or session
SELECT authn.set_tenant('acme-corp');
```

*Source: authn/src/functions/080_rls.sql:1*

---

## Sessions

### authn.create_session

```sql
authn.create_session(p_user_id: uuid, p_token_hash: text, p_expires_in: interval, p_ip_address: inet, p_user_agent: text, p_namespace: text) -> uuid
```

Create a session after successful login

**Parameters:**
- `p_token_hash`: SHA-256 hash of the session token (you generate the token, hash it, store hash here, send raw token to client)
- `p_expires_in`: Session duration (default 7 days)

**Returns:** Session ID

**Example:**
```sql
-- After verifying password
SELECT authn.create_session(user_id, sha256(token), '7 days', '1.2.3.4');
```

*Source: authn/src/functions/020_sessions.sql:1*

---

### authn.extend_session

```sql
authn.extend_session(p_token_hash: text, p_extend_by: interval, p_namespace: text) -> timestamptz
```

Extend session absolute timeout (for "remember me", not idle timeout)

**Returns:** New expires_at, or NULL if session invalid

**Example:**
```sql
SELECT authn.extend_session(token_hash, '30 days'); -- "remember me"
```

*Source: authn/src/functions/020_sessions.sql:81*

---

### authn.list_sessions

```sql
authn.list_sessions(p_user_id: uuid, p_namespace: text) -> table(session_id: uuid, created_at: timestamptz, expires_at: timestamptz, ip_address: inet, user_agent: text)
```

List active sessions for "manage devices" UI

**Returns:** Active sessions with IP, user agent, timestamps (no token hash)

**Example:**
```sql
SELECT * FROM authn.list_sessions(user_id);
```

*Source: authn/src/functions/020_sessions.sql:197*

---

### authn.revoke_all_sessions

```sql
authn.revoke_all_sessions(p_user_id: uuid, p_namespace: text) -> int4
```

Log out all sessions for a user (password change, security concern)

**Returns:** Count of sessions revoked

**Example:**
```sql
SELECT authn.revoke_all_sessions(user_id); -- "Log out everywhere"
```

*Source: authn/src/functions/020_sessions.sql:162*

---

### authn.revoke_session

```sql
authn.revoke_session(p_token_hash: text, p_namespace: text) -> bool
```

Log out a specific session

**Example:**
```sql
SELECT authn.revoke_session(token_hash); -- User clicks "log out"
```

*Source: authn/src/functions/020_sessions.sql:124*

---

### authn.revoke_session_by_id

```sql
authn.revoke_session_by_id(p_session_id: uuid, p_user_id: uuid, p_namespace: text) -> bool
```

Revoke a specific session by ID (for "manage devices" UI)

**Parameters:**
- `p_session_id`: Session ID to revoke
- `p_user_id`: User ID (for ownership verification)

**Returns:** true if revoked, false if not found or not owned by user

**Example:**
```sql
SELECT authn.revoke_session_by_id(session_id, user_id);
```

*Source: authn/src/functions/020_sessions.sql:233*

---

### authn.validate_session

```sql
authn.validate_session(p_token_hash: text, p_namespace: text) -> table(user_id: uuid, email: text, session_id: uuid)
```

Check if session is valid and get user info (hot path, no logging)

**Returns:** user_id, email, session_id if valid. Empty if expired/revoked/disabled.

**Example:**
```sql
SELECT * FROM authn.validate_session(sha256(token_from_cookie));
```

*Source: authn/src/functions/020_sessions.sql:48*

---

## Tokens

### authn.consume_token

```sql
authn.consume_token(p_token_hash: text, p_token_type: text, p_namespace: text) -> table(user_id: uuid, email: text)
```

Use a one-time token (marks as used, can't be reused)

**Returns:** user_id, email if valid. Empty if expired, already used, or wrong type.

**Example:**
```sql
SELECT * FROM authn.consume_token(sha256(token_from_url), 'password_reset');
```

*Source: authn/src/functions/030_tokens.sql:46*

---

### authn.create_token

```sql
authn.create_token(p_user_id: uuid, p_token_hash: text, p_token_type: text, p_expires_in: interval, p_namespace: text) -> uuid
```

Create a one-time token for password reset, email verification, or magic link

**Parameters:**
- `p_token_hash`: SHA-256 hash of the token (send raw token to user via email)
- `p_token_type`: One of: 'password_reset', 'email_verify', 'magic_link'

**Returns:** Token ID

**Example:**
```sql
-- Send password reset email
SELECT authn.create_token(user_id, sha256(token), 'password_reset');
```

*Source: authn/src/functions/030_tokens.sql:1*

---

### authn.invalidate_tokens

```sql
authn.invalidate_tokens(p_user_id: uuid, p_token_type: text, p_namespace: text) -> int4
```

Invalidate unused tokens (e.g., after password change, invalidate reset tokens)

**Returns:** Count of tokens invalidated

**Example:**
```sql
-- After password change, invalidate old reset tokens
SELECT authn.invalidate_tokens(user_id, 'password_reset');
```

*Source: authn/src/functions/030_tokens.sql:140*

---

### authn.verify_email

```sql
authn.verify_email(p_token_hash: text, p_namespace: text) -> table(user_id: uuid, email: text)
```

Verify email address using token from email link

**Returns:** user_id, email if valid. Sets email_verified_at automatically.

**Example:**
```sql
SELECT * FROM authn.verify_email(sha256(token_from_url));
```

*Source: authn/src/functions/030_tokens.sql:98*

---

## Users

### authn.create_user

```sql
authn.create_user(p_email: text, p_password_hash: text, p_namespace: text) -> uuid
```

Create a new user account

**Parameters:**
- `p_password_hash`: Argon2id hash from your app. NULL for SSO-only users.

**Returns:** User ID (UUID)

**Example:**
```sql
SELECT authn.create_user('alice@example.com', '$argon2id$...', 'default');
```

*Source: authn/src/functions/010_users.sql:1*

---

### authn.delete_user

```sql
authn.delete_user(p_user_id: uuid, p_namespace: text) -> bool
```

Permanently delete user and all their data (sessions, tokens, MFA)

**Returns:** True if user was found and deleted

**Example:**
```sql
SELECT authn.delete_user(user_id); -- Irreversible!
```

*Source: authn/src/functions/010_users.sql:240*

---

### authn.disable_user

```sql
authn.disable_user(p_user_id: uuid, p_namespace: text) -> bool
```

Disable user account and revoke all active sessions

**Returns:** True if user was found and disabled

**Example:**
```sql
SELECT authn.disable_user(user_id); -- User can no longer log in
```

*Source: authn/src/functions/010_users.sql:159*

---

### authn.enable_user

```sql
authn.enable_user(p_user_id: uuid, p_namespace: text) -> bool
```

Re-enable a disabled user account

**Example:**
```sql
SELECT authn.enable_user(user_id);
```

*Source: authn/src/functions/010_users.sql:206*

---

### authn.get_user

```sql
authn.get_user(p_user_id: uuid, p_namespace: text) -> table(user_id: uuid, email: text, email_verified_at: timestamptz, disabled_at: timestamptz, created_at: timestamptz, updated_at: timestamptz)
```

Get user by ID (does not return password hash)

**Example:**
```sql
SELECT * FROM authn.get_user('550e8400-e29b-41d4-a716-446655440000');
```

*Source: authn/src/functions/010_users.sql:37*

---

### authn.get_user_by_email

```sql
authn.get_user_by_email(p_email: text, p_namespace: text) -> table(user_id: uuid, email: text, email_verified_at: timestamptz, disabled_at: timestamptz, created_at: timestamptz, updated_at: timestamptz)
```

Look up user by email (normalized to lowercase)

**Example:**
```sql
SELECT * FROM authn.get_user_by_email('Alice@Example.com');
```

*Source: authn/src/functions/010_users.sql:71*

---

### authn.list_users

```sql
authn.list_users(p_namespace: text, p_limit: int4, p_cursor: uuid) -> table(user_id: uuid, email: text, email_verified_at: timestamptz, disabled_at: timestamptz, created_at: timestamptz, updated_at: timestamptz)
```

List users with cursor-based pagination

**Parameters:**
- `p_limit`: Max users per page (default 100, max 1000)
- `p_cursor`: User ID to start after (for pagination)

**Example:**
```sql
SELECT * FROM authn.list_users('default', 50, NULL); -- First page
```

*Source: authn/src/functions/010_users.sql:284*

---

### authn.update_email

```sql
authn.update_email(p_user_id: uuid, p_new_email: text, p_namespace: text) -> bool
```

Change user's email address (clears email_verified_at)

**Returns:** True if user was found and updated

**Example:**
```sql
SELECT authn.update_email(user_id, 'new@example.com');
```

*Source: authn/src/functions/010_users.sql:108*

---
