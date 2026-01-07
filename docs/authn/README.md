# Authn API Reference

## Python SDK

| Function | Description |
|----------|-------------|
| [`add_mfa`](sdk.md#add_mfa) | Add an MFA method for a user. |
| [`cleanup_expired`](sdk.md#cleanup_expired) | Clean up expired sessions, tokens, and old login attempts. |
| [`clear_actor`](sdk.md#clear_actor) | Clear actor context. |
| [`clear_attempts`](sdk.md#clear_attempts) | Clear login attempts for an email. Returns count deleted. |
| [`consume_token`](sdk.md#consume_token) | Consume a one-time token. |
| [`create_api_key`](sdk.md#create_api_key) | Create an API key for programmatic access. |
| [`create_session`](sdk.md#create_session) | Create a new session. |
| [`create_token`](sdk.md#create_token) | Create a one-time use token. |
| [`create_user`](sdk.md#create_user) | Create a new user. |
| [`delete_user`](sdk.md#delete_user) | Permanently delete a user and all associated data. |
| [`disable_user`](sdk.md#disable_user) | Disable user and revoke all their sessions. |
| [`enable_user`](sdk.md#enable_user) | Re-enable a disabled user. |
| [`extend_session`](sdk.md#extend_session) | Extend session expiration. |
| [`get_audit_events`](sdk.md#get_audit_events) | Query audit events. |
| [`get_credentials`](sdk.md#get_credentials) | Get credentials for login verification. |
| [`get_mfa`](sdk.md#get_mfa) | Get MFA secrets for verification. Returns secrets! |
| [`get_recent_attempts`](sdk.md#get_recent_attempts) | Get recent login attempts for an email. |
| [`get_stats`](sdk.md#get_stats) | Get namespace statistics. |
| [`get_user`](sdk.md#get_user) | Get user by ID. Does not return password_hash. |
| [`get_user_by_email`](sdk.md#get_user_by_email) | Get user by email. Does not return password_hash. |
| [`has_mfa`](sdk.md#has_mfa) | Check if user has any MFA method enabled. |
| [`invalidate_tokens`](sdk.md#invalidate_tokens) | Invalidate all unused tokens of a type for a user. |
| [`is_locked_out`](sdk.md#is_locked_out) | Check if an email is locked out due to too many failed attempts. |
| [`list_api_keys`](sdk.md#list_api_keys) | List active API keys for a user. Does not return key_hash. |
| [`list_mfa`](sdk.md#list_mfa) | List MFA methods. Does NOT return secrets. |
| [`list_sessions`](sdk.md#list_sessions) | List active sessions for a user. Does not return token_hash. |
| [`list_users`](sdk.md#list_users) | List users with pagination. |
| [`record_login_attempt`](sdk.md#record_login_attempt) | Record a login attempt. |
| [`record_mfa_use`](sdk.md#record_mfa_use) | Record that an MFA method was used. |
| [`remove_mfa`](sdk.md#remove_mfa) | Remove an MFA method. |
| [`revoke_all_api_keys`](sdk.md#revoke_all_api_keys) | Revoke all API keys for a user. Returns count revoked. |
| [`revoke_all_sessions`](sdk.md#revoke_all_sessions) | Revoke all sessions for a user. Returns count revoked. |
| [`revoke_api_key`](sdk.md#revoke_api_key) | Revoke an API key. |
| [`revoke_other_sessions`](sdk.md#revoke_other_sessions) | Revoke all sessions except the specified one ("sign out other devices"). |
| [`revoke_session`](sdk.md#revoke_session) | Revoke a session. |
| [`revoke_session_by_id`](sdk.md#revoke_session_by_id) | Revoke a session by ID (for manage devices UI). |
| [`set_actor`](sdk.md#set_actor) | Set actor context for audit logging with authn-specific fields. |
| [`update_email`](sdk.md#update_email) | Update user's email. Clears email_verified_at. |
| [`update_password`](sdk.md#update_password) | Update user's password hash. |
| [`validate_api_key`](sdk.md#validate_api_key) | Validate an API key. |
| [`validate_session`](sdk.md#validate_session) | Validate a session token. |
| [`verify_email`](sdk.md#verify_email) | Verify email using a token. |

## SQL Functions

| Function | Description |
|----------|-------------|
| [`authn.create_api_key`](sql.md#authncreate_api_key) | Create an API key for programmatic access |
| [`authn.list_api_keys`](sql.md#authnlist_api_keys) | List API keys for a user (for management UI) |
| [`authn.revoke_all_api_keys`](sql.md#authnrevoke_all_api_keys) | Revoke all API keys for a user |
| [`authn.revoke_api_key`](sql.md#authnrevoke_api_key) | Revoke an API key |
| [`authn.validate_api_key`](sql.md#authnvalidate_api_key) | Validate an API key and get owner info (hot path) |
| [`authn.clear_actor`](sql.md#authnclear_actor) | Clear actor context |
| [`authn.create_audit_partition`](sql.md#authncreate_audit_partition) | Create a monthly partition for audit events |
| [`authn.drop_audit_partitions`](sql.md#authndrop_audit_partitions) | Delete old audit partitions (default: keep 7 years for compliance) |
| [`authn.ensure_audit_partitions`](sql.md#authnensure_audit_partitions) | Create partitions for upcoming months (run monthly via cron) |
| [`authn.set_actor`](sql.md#authnset_actor) | Tag audit events with who made the change (call before user operations) |
| [`authn.get_credentials`](sql.md#authnget_credentials) | Get password hash for login verification (only function that returns hash) |
| [`authn.update_password`](sql.md#authnupdate_password) | Update user's password hash (after password change or reset) |
| [`authn.clear_attempts`](sql.md#authnclear_attempts) | Clear login attempts to unlock a user (admin function) |
| [`authn.get_recent_attempts`](sql.md#authnget_recent_attempts) | Get recent login attempts for admin UI or user security page |
| [`authn.is_locked_out`](sql.md#authnis_locked_out) | Check if email is locked out due to too many failed attempts |
| [`authn.record_login_attempt`](sql.md#authnrecord_login_attempt) | Record a login attempt (success or failure) for lockout tracking |
| [`authn.add_mfa`](sql.md#authnadd_mfa) | Add an MFA method (TOTP, WebAuthn, or recovery codes) |
| [`authn.get_mfa`](sql.md#authnget_mfa) | Get MFA secrets for verification (returns raw secrets) |
| [`authn.has_mfa`](sql.md#authnhas_mfa) | Check if user has any MFA method configured |
| [`authn.list_mfa`](sql.md#authnlist_mfa) | List user's MFA methods for "manage security" UI (no secrets) |
| [`authn.record_mfa_use`](sql.md#authnrecord_mfa_use) | Record successful MFA verification (updates last_used_at) |
| [`authn.remove_mfa`](sql.md#authnremove_mfa) | Remove an MFA method |
| [`authn.cleanup_expired`](sql.md#authncleanup_expired) | Delete expired sessions, tokens, API keys, and old login attempts (run via cron) |
| [`authn.get_stats`](sql.md#authnget_stats) | Get namespace statistics for monitoring dashboards |
| [`authn.clear_tenant`](sql.md#authnclear_tenant) | Clear tenant context. Queries return no rows (fail-closed for safety). |
| [`authn.set_tenant`](sql.md#authnset_tenant) | Set the tenant context for Row-Level Security |
| [`authn.create_session`](sql.md#authncreate_session) | Create a session after successful login |
| [`authn.extend_session`](sql.md#authnextend_session) | Extend session absolute timeout (for "remember me", not idle timeout) |
| [`authn.list_sessions`](sql.md#authnlist_sessions) | List active sessions for "manage devices" UI |
| [`authn.revoke_all_sessions`](sql.md#authnrevoke_all_sessions) | Log out all sessions for a user (password change, security concern) |
| [`authn.revoke_other_sessions`](sql.md#authnrevoke_other_sessions) | Log out all sessions except the current one ("sign out other devices") |
| [`authn.revoke_session`](sql.md#authnrevoke_session) | Log out a specific session |
| [`authn.revoke_session_by_id`](sql.md#authnrevoke_session_by_id) | Revoke a specific session by ID (for "manage devices" UI) |
| [`authn.validate_session`](sql.md#authnvalidate_session) | Check if session is valid and get user info (hot path, no logging) |
| [`authn.consume_token`](sql.md#authnconsume_token) | Use a one-time token (marks as used, can't be reused) |
| [`authn.create_token`](sql.md#authncreate_token) | Create a one-time token for password reset, email verification, or magic link |
| [`authn.invalidate_tokens`](sql.md#authninvalidate_tokens) | Invalidate unused tokens (e.g., after password change, invalidate reset tokens) |
| [`authn.verify_email`](sql.md#authnverify_email) | Verify email address using token from email link |
| [`authn.create_user`](sql.md#authncreate_user) | Create a new user account |
| [`authn.delete_user`](sql.md#authndelete_user) | Permanently delete user and all their data (sessions, tokens, MFA) |
| [`authn.disable_user`](sql.md#authndisable_user) | Disable user account and revoke all active sessions |
| [`authn.enable_user`](sql.md#authnenable_user) | Re-enable a disabled user account |
| [`authn.get_user`](sql.md#authnget_user) | Get user by ID (does not return password hash) |
| [`authn.get_user_by_email`](sql.md#authnget_user_by_email) | Look up user by email (normalized to lowercase) |
| [`authn.list_users`](sql.md#authnlist_users) | List users with cursor-based pagination |
| [`authn.update_email`](sql.md#authnupdate_email) | Change user's email address (clears email_verified_at) |
