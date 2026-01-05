"""Base client for postkit modules.

Provides shared database operations, error handling, tenant context,
and actor context management used by AuthnClient, AuthzClient, and ConfigClient.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import psycopg


class PostkitError(Exception):
    """Base exception for postkit operations."""


class BaseClient(ABC):
    """Abstract base class for postkit clients.

    Provides shared functionality:
    - Database helper methods (_scalar, _fetchall, _write_scalar)
    - Error handling
    - Tenant context (RLS)
    - Actor context for audit logging

    Subclasses must define:
    - _schema: The PostgreSQL schema name ("authn", "authz", "config")
    - _error_class: The exception class to raise on errors
    - _apply_actor_context(): How to apply actor context via SQL
    """

    _schema: str  # "authn", "authz", "config"
    _error_class: type[Exception] = PostkitError

    def __init__(self, cursor, namespace: str):
        """Initialize the client.

        Args:
            cursor: A DB-API 2.0 cursor (psycopg2, psycopg3, etc.)
            namespace: Tenant namespace for multi-tenancy
        """
        self.cursor = cursor
        self.namespace = namespace
        # Core actor context fields (shared by all clients)
        self._actor_id: str | None = None
        self._request_id: str | None = None
        self._on_behalf_of: str | None = None
        self._reason: str | None = None
        # Set tenant context for RLS
        self.cursor.execute(f"SELECT {self._schema}.set_tenant(%s)", (namespace,))

    def _handle_error(self, e: psycopg.Error) -> None:
        """Convert psycopg errors to SDK exceptions."""
        raise self._error_class(str(e)) from e

    def _scalar(self, sql: str, params: tuple):
        """Execute SQL and return single scalar value."""
        try:
            self.cursor.execute(sql, params)
            result = self.cursor.fetchone()
            return result[0] if result else None
        except psycopg.Error as e:
            self._handle_error(e)

    def _fetchall(self, sql: str, params: tuple) -> list[dict]:
        """Execute SQL and return all rows as list of dicts."""
        try:
            self.cursor.execute(sql, params)
            columns = [desc[0] for desc in self.cursor.description]
            return [dict(zip(columns, row)) for row in self.cursor.fetchall()]
        except psycopg.Error as e:
            self._handle_error(e)

    def _fetchall_raw(self, sql: str, params: tuple) -> list[tuple]:
        """Execute SQL and return all rows as raw tuples."""
        try:
            self.cursor.execute(sql, params)
            return self.cursor.fetchall()
        except psycopg.Error as e:
            self._handle_error(e)

    @abstractmethod
    def _apply_actor_context(self) -> None:
        """Apply actor context via schema-specific SQL.

        Subclasses implement this to call their schema's set_actor() function
        with the appropriate parameters.
        """
        ...

    def _write_with_actor(self, executor):
        """Execute a write operation with actor context for audit logging.

        Actor context uses PostgreSQL's transaction-local settings (set_config with
        is_local=true). This means the actor info only persists within a transaction.

        When actor context is set:
        - In autocommit mode: Each statement is its own transaction, so we must:
          1. Begin an explicit transaction
          2. Set actor context
          3. Execute the write (triggers capture actor from settings)
          4. Commit
        - In manual transaction mode: The caller controls the transaction, so we just
          set the actor context and let them commit when ready.

        Note: This method assumes single-threaded access to the cursor.
        psycopg cursors are not thread-safe; do not share clients across threads.

        Args:
            executor: Callable that performs the actual SQL execution and returns result
        """
        if self._actor_id is None:
            return executor()

        # Check if already in a transaction (psycopg transaction_status: 0 = idle)
        in_transaction = self.cursor.connection.info.transaction_status != 0

        if in_transaction:
            # Caller manages transaction - just set actor context
            self._apply_actor_context()
            return executor()

        # Autocommit mode - wrap in transaction so actor context persists
        try:
            self.cursor.execute("BEGIN")
            self._apply_actor_context()
            result = executor()
            self.cursor.execute("COMMIT")
            return result
        except Exception:
            self.cursor.execute("ROLLBACK")
            raise

    def _write_scalar(self, sql: str, params: tuple):
        """Execute a write operation with actor context, returning single scalar value."""
        return self._write_with_actor(lambda: self._scalar(sql, params))

    def _write_row(self, sql: str, params: tuple) -> tuple | None:
        """Execute a write operation with actor context, returning single row.

        Like _write_scalar but returns full row for multi-column results.
        Used by operations that return composite types (balance + entry_id, etc.)
        """

        def execute():
            self.cursor.execute(sql, params)
            return self.cursor.fetchone()

        return self._write_with_actor(execute)

    def set_actor(
        self,
        actor_id: str,
        request_id: str | None = None,
        on_behalf_of: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Set actor context for audit logging.

        Call this before performing operations to record who made changes.
        Context persists until clear_actor() is called or client is discarded.

        Args:
            actor_id: The actor making changes (e.g., 'user:admin-bob', 'agent:support-bot')
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

    def get_audit_events(
        self,
        limit: int = 100,
        event_type: str | None = None,
        **filters,
    ) -> list[dict]:
        """Query audit events with optional filters.

        Args:
            limit: Maximum number of events to return (default 100)
            event_type: Filter by event type (e.g., 'tuple_created', 'entry_created')
            **filters: Additional column=value filters (schema-specific)

        Returns:
            List of audit event dictionaries
        """
        conditions = ["namespace = %s"]
        params: list = [self.namespace]

        if event_type is not None:
            conditions.append("event_type = %s")
            params.append(event_type)

        # Handle schema-specific filters
        for col, val in filters.items():
            if val is not None:
                conditions.append(f"{col} = %s")
                params.append(val)

        params.append(limit)

        sql = f"""
            SELECT *
            FROM {self._schema}.audit_events
            WHERE {" AND ".join(conditions)}
            ORDER BY event_time DESC, id DESC
            LIMIT %s
        """

        self.cursor.execute(sql, tuple(params))
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in self.cursor.fetchall()]
