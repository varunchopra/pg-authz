"""Postkit Config SDK - Versioned configuration management."""

from __future__ import annotations

import json
from typing import Any

from postkit.base import BaseClient, PostkitError


class ConfigError(PostkitError):
    """Exception for config operations."""


class ConfigClient(BaseClient):
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

    _schema = "config"
    _error_class = ConfigError

    def __init__(self, cursor, namespace: str):
        """Initialize the config client.

        Args:
            cursor: A DB-API 2.0 cursor (psycopg2, psycopg3, etc.)
            namespace: Tenant namespace for multi-tenancy
        """
        super().__init__(cursor, namespace)

    def _apply_actor_context(self) -> None:
        """Apply actor context via config.set_actor()."""
        self.cursor.execute(
            """SELECT config.set_actor(
                p_actor_id := %s,
                p_request_id := %s,
                p_on_behalf_of := %s,
                p_reason := %s
            )""",
            (self._actor_id, self._request_id, self._on_behalf_of, self._reason),
        )

    def set(self, key: str, value: Any) -> int:
        """Create a new version and activate it.

        Args:
            key: Config key (e.g., 'prompts/support-bot', 'flags/checkout')
            value: Config value (will be stored as JSONB)

        Returns:
            New version number
        """
        return self._fetch_val(
            "SELECT config.set(%s, %s::jsonb, %s)",
            (key, json.dumps(value), self.namespace),
            write=True,
        )

    def get(self, key: str, version: int | None = None) -> dict | None:
        """Get config entry.

        Args:
            key: Config key
            version: Specific version (default: active version)

        Returns:
            Dict with 'value', 'version', 'created_at' or None if not found
        """
        return self._fetch_one(
            "SELECT value, version, created_at FROM config.get(%s, %s, %s)",
            (key, version, self.namespace),
        )

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
        return self._fetch_all(
            "SELECT key, value, version, created_at FROM config.get_batch(%s, %s)",
            (keys, self.namespace),
        )

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
        return self._fetch_val(
            "SELECT config.get_path(%s, %s, %s)",
            (key, list(path), self.namespace),
        )

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
        return self._fetch_val(
            "SELECT config.merge(%s, %s::jsonb, %s)",
            (key, json.dumps(changes), self.namespace),
            write=True,
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
        return self._fetch_all(
            "SELECT key, value, version, created_at FROM config.search(%s::jsonb, %s, %s, %s)",
            (json.dumps(contains), prefix, self.namespace, limit),
        )

    def activate(self, key: str, version: int) -> bool:
        """Activate a specific version.

        Args:
            key: Config key
            version: Version to activate

        Returns:
            True if version was found and activated
        """
        return self._fetch_val(
            "SELECT config.activate(%s, %s, %s)",
            (key, version, self.namespace),
            write=True,
        )

    def rollback(self, key: str) -> int | None:
        """Rollback to previous version.

        Args:
            key: Config key

        Returns:
            New active version number, or None if no previous version
        """
        return self._fetch_val(
            "SELECT config.rollback(%s, %s)",
            (key, self.namespace),
            write=True,
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
        return self._fetch_all(
            "SELECT key, value, version, created_at FROM config.list(%s, %s, %s, %s)",
            (prefix, self.namespace, limit, cursor),
        )

    def history(self, key: str, limit: int = 50) -> list[dict]:
        """Get version history for a key.

        Args:
            key: Config key
            limit: Max versions to return

        Returns:
            List of dicts with 'version', 'value', 'is_active', 'created_at', 'created_by'
        """
        return self._fetch_all(
            "SELECT version, value, is_active, created_at, created_by FROM config.history(%s, %s, %s)",
            (key, self.namespace, limit),
        )

    def delete(self, key: str) -> int:
        """Delete all versions of a config entry.

        Args:
            key: Config key

        Returns:
            Count of versions deleted
        """
        return self._fetch_val(
            "SELECT config.delete(%s, %s)", (key, self.namespace), write=True
        )

    def delete_version(self, key: str, version: int) -> bool:
        """Delete a specific version (cannot delete active version).

        Args:
            key: Config key
            version: Version to delete

        Returns:
            True if deleted
        """
        return self._fetch_val(
            "SELECT config.delete_version(%s, %s, %s)",
            (key, version, self.namespace),
            write=True,
        )

    def exists(self, key: str) -> bool:
        """Check if a config key exists.

        Args:
            key: Config key

        Returns:
            True if key exists and has an active version
        """
        return self._fetch_val("SELECT config.exists(%s, %s)", (key, self.namespace))

    def get_stats(self) -> dict:
        """Get namespace statistics.

        Returns:
            Dict with 'total_keys', 'total_versions', 'keys_by_prefix'
        """
        row = self._fetch_one(
            "SELECT total_keys, total_versions, keys_by_prefix FROM config.get_stats(%s)",
            (self.namespace,),
        )
        if row is None:
            return {"total_keys": 0, "total_versions": 0, "keys_by_prefix": {}}
        # Handle NULL keys_by_prefix from SQL
        return {**row, "keys_by_prefix": row["keys_by_prefix"] or {}}

    def cleanup_old_versions(self, keep_versions: int = 10) -> int:
        """Delete old inactive versions, keeping N most recent per key.

        Args:
            keep_versions: Number of inactive versions to keep per key (default 10)

        Returns:
            Count of versions deleted
        """
        return self._fetch_val(
            "SELECT config.cleanup_old_versions(%s, %s)",
            (keep_versions, self.namespace),
            write=True,
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
        return super().get_audit_events(limit=limit, event_type=event_type, key=key)
