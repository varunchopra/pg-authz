"""Base client for postkit modules.

Provides shared database operations, error handling, tenant context,
and actor context management used by AuthnClient, AuthzClient, and ConfigClient.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar

import psycopg
from psycopg.rows import dict_row, kwargs_row

T = TypeVar("T")

# Known row factories that return dict-like objects (iteration yields keys, not values)
_DICT_LIKE_FACTORIES = frozenset({dict_row, kwargs_row})

# SQLSTATE to exception class mapping
# Reference: https://www.postgresql.org/docs/current/errcodes-appendix.html
_SQLSTATE_EXCEPTIONS: dict[
    str, type[PostkitError]
] = {}  # Populated after class definitions


class PostkitError(Exception):
    """Base exception for postkit operations."""

    def __init__(self, message: str, sqlstate: str | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate


class UniqueViolationError(PostkitError):
    """Raised when a unique constraint is violated (e.g., duplicate email)."""

    pass


class ForeignKeyViolationError(PostkitError):
    """Raised when a foreign key constraint is violated."""

    pass


class CheckViolationError(PostkitError):
    """Raised when a check constraint is violated (e.g., invalid format)."""

    pass


# Populate SQLSTATE mapping after classes are defined
_SQLSTATE_EXCEPTIONS.update(
    {
        "23505": UniqueViolationError,  # unique_violation
        "23503": ForeignKeyViolationError,  # foreign_key_violation
        "23514": CheckViolationError,  # check_violation
    }
)


class BaseClient(ABC):
    """Abstract base class for postkit clients.

    Provides shared functionality:
    - Database helper methods (_scalar, _fetchall, _write_scalar)
    - Error handling with SQLSTATE preservation
    - Tenant context (RLS)
    - Actor context for audit logging

    Subclasses must define:
    - _schema: The PostgreSQL schema name ("authn", "authz", "config", "meter")
    - _error_class: The exception class to raise on errors
    - _apply_actor_context(): How to apply actor context via SQL
    """

    _schema: str  # Must be a valid SQL identifier
    _error_class: type[PostkitError] = PostkitError

    def __init__(self, cursor: psycopg.Cursor[tuple[Any, ...]], namespace: str) -> None:
        """Initialize the client.

        Args:
            cursor: A psycopg3 cursor with default (tuple) row factory.
                Do NOT use row_factory=dict_row - the SDK returns dicts automatically.
            namespace: Tenant namespace for multi-tenancy

        Raises:
            ValueError: If cursor has a dict-returning row factory, or schema is invalid.
        """
        # S16: Validate schema name is a safe identifier
        if not self._schema.isidentifier():
            raise ValueError(f"Invalid schema name: {self._schema}")

        # S13: Check against known dict-returning factories by identity
        if (
            hasattr(cursor, "row_factory")
            and cursor.row_factory in _DICT_LIKE_FACTORIES
        ):
            raise ValueError(
                "postkit requires tuple row factory (the default). "
                "Remove row_factory=dict_row or kwargs_row from your cursor/connection. "
                "The SDK returns dicts automatically by combining column names with tuple values."
            )

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
        """Convert psycopg errors to SDK exceptions, preserving SQLSTATE.

        Uses specific exception subclasses for common database errors
        (unique violation, foreign key violation, etc.) to enable
        precise error handling by callers.
        """
        sqlstate = getattr(e, "sqlstate", None)
        message = str(e)

        # Use specific exception class if we have one for this SQLSTATE
        exc_class = _SQLSTATE_EXCEPTIONS.get(sqlstate, self._error_class)

        raise exc_class(message, sqlstate) from e

    def _scalar(self, sql: str, params: tuple[Any, ...]) -> Any:
        """Execute SQL and return single scalar value."""
        try:
            self.cursor.execute(sql, params)
            result = self.cursor.fetchone()
            return result[0] if result else None
        except psycopg.Error as e:
            self._handle_error(e)

    def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        """Execute SQL and return all rows as list of dicts."""
        try:
            self.cursor.execute(sql, params)
            columns = [desc[0] for desc in self.cursor.description]
            rows = self.cursor.fetchall()

            # S13: Defensive runtime check for dict-like rows
            if rows and isinstance(rows[0], dict):
                raise self._error_class(
                    "Cursor returned dict rows. postkit requires tuple row factory. "
                    "The SDK builds dicts internally from tuple rows.",
                    sqlstate=None,
                )

            return [dict(zip(columns, row)) for row in rows]
        except psycopg.Error as e:
            self._handle_error(e)

    def _fetchall_raw(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
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

    def _write_with_actor(self, executor: Callable[[], T]) -> T:
        """Execute a write operation with actor context for audit logging.

        Actor context uses PostgreSQL's transaction-local settings (SET LOCAL).
        This requires a transaction to persist between setting context and executing.

        - In autocommit mode: We wrap in an explicit transaction
        - In manual transaction mode: Caller controls the transaction

        Note: This method assumes single-threaded cursor access.
        psycopg cursors are not thread-safe; do not share clients across threads.

        Args:
            executor: Callable that performs the actual SQL execution and returns result
        """
        if self._actor_id is None:
            return executor()

        conn = self.cursor.connection
        in_transaction = conn.info.transaction_status != 0

        if in_transaction:
            # Caller manages transaction - just set actor context
            self._apply_actor_context()
            return executor()
        else:
            # S15: Use psycopg's transaction manager for proper cleanup
            with conn.transaction():
                self._apply_actor_context()
                return executor()

    def _write_scalar(self, sql: str, params: tuple[Any, ...]) -> Any:
        """Execute a write operation with actor context, returning single scalar value."""
        return self._write_with_actor(lambda: self._scalar(sql, params))

    def _write_row(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        """Execute a write operation with actor context, returning single row.

        Like _write_scalar but returns full row for multi-column results.
        Used by operations that return composite types (balance + entry_id, etc.)
        """

        def execute() -> tuple[Any, ...] | None:
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
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Query audit events with optional filters.

        Args:
            limit: Maximum number of events to return (default 100)
            event_type: Filter by event type (e.g., 'tuple_created', 'entry_created')
            **filters: Additional column=value filters (schema-specific)

        Returns:
            List of audit event dictionaries
        """
        conditions = ["namespace = %s"]
        params: list[Any] = [self.namespace]

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
