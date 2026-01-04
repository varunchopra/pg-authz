"""Postkit Config SDK - Versioned configuration management."""

from __future__ import annotations

import json
from typing import Any


class ConfigClient:
    """Client for Postkit config module.

    Manages versioned configuration including prompts, feature flags, secrets,
    and settings. All config types use the same API — differentiate by key
    naming conventions.

    Example:
        config = ConfigClient(cursor, namespace="acme")

        # Prompts
        config.set("prompts/support-bot", {
            "template": "You are a helpful assistant...",
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.7
        })

        # Feature flags
        config.set("flags/new-checkout", {"enabled": True, "rollout": 0.5})

        # Secrets (caller encrypts)
        config.set("secrets/OPENAI_API_KEY", {"encrypted": "aes256gcm:..."})

        # Get active version
        prompt = config.get("prompts/support-bot")

        # Rollback to previous version
        config.rollback("prompts/support-bot")
    """

    def __init__(self, cursor, namespace: str = "default"):
        """Initialize the config client.

        Args:
            cursor: A DB-API 2.0 cursor (psycopg2, psycopg3, etc.)
            namespace: Tenant namespace for multi-tenancy
        """
        self._cursor = cursor
        self._namespace = namespace
        # Actor context stored as instance state (applied per-operation)
        self._actor_id: str | None = None
        self._request_id: str | None = None
        self._on_behalf_of: str | None = None
        self._reason: str | None = None
        # Set tenant context for RLS
        self._cursor.execute("SELECT config.set_tenant(%s)", (namespace,))

    def _scalar(self, sql: str, params: tuple):
        """Execute SQL and return single scalar value."""
        self._cursor.execute(sql, params)
        result = self._cursor.fetchone()
        return result[0] if result else None

    def _write_scalar(self, sql: str, params: tuple):
        """Execute a write operation with actor context for audit logging.

        Actor context uses PostgreSQL's transaction-local settings. When actor
        context is set, we wrap the operation in a transaction to ensure the
        audit trigger captures the actor information.
        """
        if self._actor_id is None:
            return self._scalar(sql, params)

        # Check if already in a transaction (psycopg transaction_status: 0 = idle)
        in_transaction = self._cursor.connection.info.transaction_status != 0

        if in_transaction:
            # Caller manages transaction - just set actor context
            self._cursor.execute(
                "SELECT config.set_actor(%s, %s, %s, %s)",
                (self._actor_id, self._request_id, self._on_behalf_of, self._reason),
            )
            return self._scalar(sql, params)

        # Autocommit mode - wrap in transaction so actor context persists
        try:
            self._cursor.execute("BEGIN")
            self._cursor.execute(
                "SELECT config.set_actor(%s, %s, %s, %s)",
                (self._actor_id, self._request_id, self._on_behalf_of, self._reason),
            )
            result = self._scalar(sql, params)
            self._cursor.execute("COMMIT")
            return result
        except Exception:
            self._cursor.execute("ROLLBACK")
            raise

    def set(self, key: str, value: Any) -> int:
        """Create a new version and activate it.

        Args:
            key: Config key (e.g., 'prompts/support-bot', 'flags/checkout')
            value: Config value (will be stored as JSONB)

        Returns:
            New version number
        """
        return self._write_scalar(
            "SELECT config.set(%s, %s::jsonb, %s)",
            (key, json.dumps(value), self._namespace),
        )

    def get(self, key: str, version: int | None = None) -> dict | None:
        """Get config entry.

        Args:
            key: Config key
            version: Specific version (default: active version)

        Returns:
            Dict with 'value', 'version', 'created_at' or None if not found
        """
        self._cursor.execute(
            "SELECT value, version, created_at FROM config.get(%s, %s, %s)",
            (key, version, self._namespace),
        )
        row = self._cursor.fetchone()
        if row is None:
            return None
        return {"value": row[0], "version": row[1], "created_at": row[2]}

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get just the value (convenience method).

        Args:
            key: Config key
            default: Default value if key doesn't exist

        Returns:
            The config value, or default if not found
        """
        result = self.get(key)
        if result is None:
            return default
        return result["value"]

    def get_batch(self, keys: list[str]) -> list[dict]:
        """Get multiple config entries in one query.

        Args:
            keys: List of config keys to fetch

        Returns:
            List of dicts with 'key', 'value', 'version', 'created_at'
        """
        self._cursor.execute(
            "SELECT key, value, version, created_at FROM config.get_batch(%s, %s)",
            (keys, self._namespace),
        )
        return [
            {"key": row[0], "value": row[1], "version": row[2], "created_at": row[3]}
            for row in self._cursor.fetchall()
        ]

    def get_path(self, key: str, *path: str) -> Any:
        """Get a specific path within a config value.

        Args:
            key: Config key
            *path: Path segments (e.g., "model", "name" for {"model": {"name": ...}})

        Returns:
            The value at the path, or None if not found

        Example:
            config.get_path("prompts/bot", "temperature")
            config.get_path("flags/checkout", "rollout")
            config.get_path("settings/model", "params", "temperature")
        """
        self._cursor.execute(
            "SELECT config.get_path(%s, %s, %s)",
            (key, list(path), self._namespace),
        )
        row = self._cursor.fetchone()
        return row[0] if row else None

    def merge(self, key: str, changes: dict) -> int:
        """Merge changes into config, creating new version.

        Performs a shallow merge - top-level keys in changes overwrite
        existing keys, other keys are preserved.

        Args:
            key: Config key
            changes: Dict of fields to merge

        Returns:
            New version number

        Example:
            config.merge("flags/checkout", {"rollout": 0.75})
            config.merge("prompts/bot", {"temperature": 0.8, "max_tokens": 2000})
        """
        return self._write_scalar(
            "SELECT config.merge(%s, %s::jsonb, %s)",
            (key, json.dumps(changes), self._namespace),
        )

    def search(
        self, contains: dict, prefix: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Find configs where value contains given JSON.

        Args:
            contains: JSON object to search for (uses containment)
            prefix: Optional key prefix filter
            limit: Max results (default 100)

        Returns:
            List of dicts with 'key', 'value', 'version', 'created_at'

        Example:
            config.search({"enabled": True})  # All enabled flags
            config.search({"model": "claude-sonnet-4-20250514"}, prefix="prompts/")
        """
        self._cursor.execute(
            "SELECT key, value, version, created_at FROM config.search(%s::jsonb, %s, %s, %s)",
            (json.dumps(contains), prefix, self._namespace, limit),
        )
        return [
            {"key": row[0], "value": row[1], "version": row[2], "created_at": row[3]}
            for row in self._cursor.fetchall()
        ]

    def activate(self, key: str, version: int) -> bool:
        """Activate a specific version.

        Args:
            key: Config key
            version: Version to activate

        Returns:
            True if version was found and activated
        """
        return self._write_scalar(
            "SELECT config.activate(%s, %s, %s)", (key, version, self._namespace)
        )

    def rollback(self, key: str) -> int | None:
        """Rollback to previous version.

        Args:
            key: Config key

        Returns:
            New active version number, or None if no previous version
        """
        return self._write_scalar(
            "SELECT config.rollback(%s, %s)", (key, self._namespace)
        )

    def list(
        self,
        prefix: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[dict]:
        """List active config entries.

        Args:
            prefix: Filter by key prefix (e.g., 'prompts/')
            limit: Max results (default 100, max 1000)
            cursor: Pagination cursor (last key from previous page)

        Returns:
            List of dicts with 'key', 'value', 'version', 'created_at'
        """
        self._cursor.execute(
            "SELECT key, value, version, created_at FROM config.list(%s, %s, %s, %s)",
            (prefix, self._namespace, limit, cursor),
        )
        return [
            {
                "key": row[0],
                "value": row[1],
                "version": row[2],
                "created_at": row[3],
            }
            for row in self._cursor.fetchall()
        ]

    def history(self, key: str, limit: int = 50) -> list[dict]:
        """Get version history for a key.

        Args:
            key: Config key
            limit: Max versions to return

        Returns:
            List of dicts with 'version', 'value', 'is_active', 'created_at', 'created_by'
        """
        self._cursor.execute(
            "SELECT version, value, is_active, created_at, created_by FROM config.history(%s, %s, %s)",
            (key, self._namespace, limit),
        )
        return [
            {
                "version": row[0],
                "value": row[1],
                "is_active": row[2],
                "created_at": row[3],
                "created_by": row[4],
            }
            for row in self._cursor.fetchall()
        ]

    def delete(self, key: str) -> int:
        """Delete all versions of a config entry.

        Args:
            key: Config key

        Returns:
            Count of versions deleted
        """
        return self._write_scalar(
            "SELECT config.delete(%s, %s)", (key, self._namespace)
        )

    def delete_version(self, key: str, version: int) -> bool:
        """Delete a specific version (cannot delete active version).

        Args:
            key: Config key
            version: Version to delete

        Returns:
            True if deleted
        """
        return self._write_scalar(
            "SELECT config.delete_version(%s, %s, %s)",
            (key, version, self._namespace),
        )

    def exists(self, key: str) -> bool:
        """Check if a config key exists.

        Args:
            key: Config key

        Returns:
            True if key exists and has an active version
        """
        self._cursor.execute("SELECT config.exists(%s, %s)", (key, self._namespace))
        row = self._cursor.fetchone()
        return row[0]

    def set_actor(
        self,
        actor_id: str,
        request_id: str | None = None,
        on_behalf_of: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Set actor context for audit logging.

        Args:
            actor_id: The actor making changes (e.g., 'user:admin-bob', 'agent:deploy-bot')
            request_id: Optional request/correlation ID for tracing
            on_behalf_of: Optional principal being represented (e.g., 'user:customer-alice')
            reason: Optional reason for the action (e.g., 'deployment:v1.2.3')
        """
        self._actor_id = actor_id
        self._request_id = request_id
        self._on_behalf_of = on_behalf_of
        self._reason = reason

    def clear_actor(self) -> None:
        """Clear actor context."""
        self._actor_id = None
        self._request_id = None
        self._on_behalf_of = None
        self._reason = None

    def get_stats(self) -> dict:
        """Get namespace statistics.

        Returns:
            Dict with 'total_keys', 'total_versions', 'keys_by_prefix'
        """
        self._cursor.execute(
            "SELECT total_keys, total_versions, keys_by_prefix FROM config.get_stats(%s)",
            (self._namespace,),
        )
        row = self._cursor.fetchone()
        if row is None:
            return {"total_keys": 0, "total_versions": 0, "keys_by_prefix": {}}
        return {
            "total_keys": row[0],
            "total_versions": row[1],
            "keys_by_prefix": row[2] or {},
        }

    def cleanup_old_versions(self, keep_versions: int = 10) -> int:
        """Delete old inactive versions, keeping N most recent per key.

        Args:
            keep_versions: Number of inactive versions to keep per key (default 10)

        Returns:
            Count of versions deleted
        """
        return self._write_scalar(
            "SELECT config.cleanup_old_versions(%s, %s)",
            (keep_versions, self._namespace),
        )

    def get_audit_events(
        self,
        limit: int = 100,
        event_type: str | None = None,
        key: str | None = None,
    ) -> list[dict]:
        """Query audit events.

        Args:
            limit: Maximum number of events to return (default 100)
            event_type: Filter by event type (e.g., 'entry_created')
            key: Filter by config key

        Returns:
            List of audit event dictionaries
        """
        conditions = ["namespace = %s"]
        params: list = [self._namespace]

        if event_type is not None:
            conditions.append("event_type = %s")
            params.append(event_type)

        if key is not None:
            conditions.append("key = %s")
            params.append(key)

        params.append(limit)

        sql = f"""
            SELECT *
            FROM config.audit_events
            WHERE {" AND ".join(conditions)}
            ORDER BY event_time DESC, id DESC
            LIMIT %s
        """

        self._cursor.execute(sql, tuple(params))
        columns = [desc[0] for desc in self._cursor.description]
        return [dict(zip(columns, row)) for row in self._cursor.fetchall()]
