"""Postkit Meter SDK - Usage tracking for metering."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from postkit.base import BaseClient, PostkitError


class MeterError(PostkitError):
    """Exception for meter operations."""


class MeterClient(BaseClient):
    """Client for Postkit meter module.

    Double-entry ledger for usage tracking with reservations.
    Meter measures. It does not price.

    Example:
        meter = MeterClient(cursor, namespace="acme")

        # Allocate quota
        meter.allocate("user-123", "llm_call", 100000, "tokens", "claude-sonnet")

        # Record consumption
        meter.consume("user-123", "llm_call", 1500, "tokens", "claude-sonnet")

        # Reserve for streaming (uncertain consumption)
        res = meter.reserve("user-123", "llm_call", 4000, "tokens", "claude-sonnet")
        # ... streaming operation ...
        meter.commit(res["reservation_id"], actual_amount=2347)

        # Check balance
        balance = meter.get_balance("user-123", "llm_call", "tokens", "claude-sonnet")
    """

    _schema = "meter"
    _error_class = MeterError

    def __init__(self, cursor, namespace: str = "default"):
        """Initialize the meter client.

        Args:
            cursor: A DB-API 2.0 cursor (psycopg2, psycopg3, etc.)
            namespace: Tenant namespace for multi-tenancy
        """
        super().__init__(cursor, namespace)

    def _apply_actor_context(self) -> None:
        """Apply actor context via meter.set_actor()."""
        self.cursor.execute(
            "SELECT meter.set_actor(%s, %s, %s, %s)",
            (self._actor_id, self._request_id, self._on_behalf_of, self._reason),
        )

    # =========================================================================
    # Recording
    # =========================================================================

    def allocate(
        self,
        user_id: str | None,
        event_type: str,
        amount: float | int | Decimal,
        unit: str,
        resource: str | None = None,
        idempotency_key: str | None = None,
        event_time: datetime | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Add quota/credits to an account.

        Args:
            user_id: User ID (None for namespace-level pool)
            event_type: Event type ('llm_call', 'api_request', etc.)
            amount: Amount to allocate (must be positive)
            unit: Unit of measurement ('tokens', 'requests', 'bytes')
            resource: Optional resource identifier ('claude-sonnet', 'gpt-4')
            idempotency_key: Optional dedup key for safe retries
            event_time: When allocation occurred (defaults to now)
            metadata: Optional JSON metadata

        Returns:
            Dict with 'balance' and 'entry_id'
        """
        self.cursor.execute(
            "SELECT balance, entry_id FROM meter.allocate(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            (
                user_id,
                event_type,
                amount,
                unit,
                resource,
                idempotency_key,
                event_time,
                json.dumps(metadata) if metadata else None,
                self.namespace,
            ),
        )
        row = self.cursor.fetchone()
        return {"balance": float(row[0]), "entry_id": row[1]}

    def consume(
        self,
        user_id: str,
        event_type: str,
        amount: float | int | Decimal,
        unit: str,
        resource: str | None = None,
        check_balance: bool = False,
        idempotency_key: str | None = None,
        event_time: datetime | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Record consumption.

        Args:
            user_id: User ID (required)
            event_type: Event type
            amount: Amount consumed (must be positive)
            unit: Unit of measurement
            resource: Optional resource identifier
            check_balance: If True, fails when insufficient balance
            idempotency_key: Optional dedup key for safe retries
            event_time: When consumption occurred (defaults to now)
            metadata: Optional JSON metadata

        Returns:
            Dict with 'success', 'balance', 'available', 'entry_id'
        """
        self.cursor.execute(
            """SELECT success, balance, available, entry_id
               FROM meter.consume(%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
            (
                user_id,
                event_type,
                amount,
                unit,
                resource,
                check_balance,
                idempotency_key,
                event_time,
                json.dumps(metadata) if metadata else None,
                self.namespace,
            ),
        )
        row = self.cursor.fetchone()
        return {
            "success": row[0],
            "balance": float(row[1]) if row[1] is not None else None,
            "available": float(row[2]) if row[2] is not None else None,
            "entry_id": row[3],
        }

    def reserve(
        self,
        user_id: str,
        event_type: str,
        amount: float | int | Decimal,
        unit: str,
        resource: str | None = None,
        ttl_seconds: int = 300,
        idempotency_key: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Reserve quota for pending operation (streaming, uncertain consumption).

        Args:
            user_id: User ID (required)
            event_type: Event type
            amount: Amount to reserve
            unit: Unit of measurement
            resource: Optional resource identifier
            ttl_seconds: Time until reservation auto-expires (default 300 = 5 min)
            idempotency_key: Optional dedup key for safe retries
            metadata: Optional JSON metadata

        Returns:
            Dict with 'granted', 'reservation_id', 'balance', 'available',
            'expires_at', 'entry_id'
        """
        self.cursor.execute(
            """SELECT granted, reservation_id, balance, available, expires_at, entry_id
               FROM meter.reserve(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
            (
                user_id,
                event_type,
                amount,
                unit,
                resource,
                ttl_seconds,
                idempotency_key,
                json.dumps(metadata) if metadata else None,
                self.namespace,
            ),
        )
        row = self.cursor.fetchone()
        return {
            "granted": row[0],
            "reservation_id": row[1],
            "balance": float(row[2]) if row[2] is not None else None,
            "available": float(row[3]) if row[3] is not None else None,
            "expires_at": row[4],
            "entry_id": row[5],
        }

    def commit(
        self,
        reservation_id: str,
        actual_amount: float | int | Decimal,
        metadata: dict | None = None,
    ) -> dict:
        """Commit a reservation with actual consumption.

        Meter measures. It does not enforce. If actual consumption exceeds
        reserved amount, the overage is recorded accurately. Caller decides
        policy (reject, allow, draw from parent pool, alert, etc.).

        Args:
            reservation_id: Reservation to commit
            actual_amount: Actual amount consumed (can be more or less than reserved)
            metadata: Optional JSON metadata

        Returns:
            Dict with 'success', 'consumed', 'released', 'reserved_amount',
            'balance', 'entry_id'

        Example:
            result = meter.commit(res_id, actual_tokens)
            overage = max(0, result["consumed"] - result["reserved_amount"])
            if overage > 0:
                handle_overage(overage)  # caller's policy
        """
        self.cursor.execute(
            """SELECT success, consumed, released, reserved_amount, balance, entry_id
               FROM meter.commit(%s, %s, %s::jsonb, %s)""",
            (
                reservation_id,
                actual_amount,
                json.dumps(metadata) if metadata else None,
                self.namespace,
            ),
        )
        row = self.cursor.fetchone()
        return {
            "success": row[0],
            "consumed": float(row[1]) if row[1] is not None else None,
            "released": float(row[2]) if row[2] is not None else None,
            "reserved_amount": float(row[3]) if row[3] is not None else None,
            "balance": float(row[4]) if row[4] is not None else None,
            "entry_id": row[5],
        }

    def release(self, reservation_id: str) -> bool:
        """Release a reservation without consuming.

        Args:
            reservation_id: Reservation to release

        Returns:
            True if released, False if not found
        """
        return self._scalar(
            "SELECT meter.release(%s, %s)", (reservation_id, self.namespace)
        )

    def adjust(
        self,
        user_id: str,
        event_type: str,
        amount: float | int | Decimal,
        unit: str,
        resource: str | None = None,
        reference_id: int | None = None,
        idempotency_key: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create an adjustment entry (correction, refund, etc.).

        Args:
            user_id: User ID
            event_type: Event type
            amount: Adjustment amount (positive = credit, negative = debit)
            unit: Unit of measurement
            resource: Optional resource identifier
            reference_id: Optional ledger entry ID being corrected
            idempotency_key: Optional dedup key for safe retries
            metadata: Optional JSON metadata

        Returns:
            Dict with 'balance' and 'entry_id'
        """
        self.cursor.execute(
            "SELECT balance, entry_id FROM meter.adjust(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            (
                user_id,
                event_type,
                amount,
                unit,
                resource,
                reference_id,
                idempotency_key,
                json.dumps(metadata) if metadata else None,
                self.namespace,
            ),
        )
        row = self.cursor.fetchone()
        return {"balance": float(row[0]), "entry_id": row[1]}

    # =========================================================================
    # Querying
    # =========================================================================

    def get_balance(
        self,
        user_id: str,
        event_type: str,
        unit: str,
        resource: str | None = None,
    ) -> dict:
        """Get current balance for an account.

        Args:
            user_id: User ID
            event_type: Event type
            unit: Unit of measurement
            resource: Optional resource identifier

        Returns:
            Dict with 'balance', 'reserved', 'available'
        """
        self.cursor.execute(
            "SELECT balance, reserved, available FROM meter.get_balance(%s, %s, %s, %s, %s)",
            (user_id, event_type, unit, resource, self.namespace),
        )
        row = self.cursor.fetchone()
        return {
            "balance": float(row[0]),
            "reserved": float(row[1]),
            "available": float(row[2]),
        }

    def get_user_balances(self, user_id: str) -> list[dict]:
        """Get all balances for a user across all event types and resources.

        Args:
            user_id: User ID

        Returns:
            List of dicts with 'event_type', 'resource', 'unit', 'balance',
            'reserved', 'available'
        """
        self.cursor.execute(
            """SELECT event_type, resource, unit, balance, reserved, available
               FROM meter.get_user_balances(%s, %s)""",
            (user_id, self.namespace),
        )
        return [
            {
                "event_type": row[0],
                "resource": row[1],
                "unit": row[2],
                "balance": float(row[3]),
                "reserved": float(row[4]),
                "available": float(row[5]),
            }
            for row in self.cursor.fetchall()
        ]

    def get_usage(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        """Get aggregated consumption for a user.

        Args:
            user_id: User ID
            start_time: Start of period
            end_time: End of period

        Returns:
            List of dicts with 'event_type', 'resource', 'unit',
            'total_consumed', 'event_count'
        """
        self.cursor.execute(
            """SELECT event_type, resource, unit, total_consumed, event_count
               FROM meter.get_usage(%s, %s, %s, %s)""",
            (user_id, start_time, end_time, self.namespace),
        )
        return [
            {
                "event_type": row[0],
                "resource": row[1],
                "unit": row[2],
                "total_consumed": float(row[3]),
                "event_count": row[4],
            }
            for row in self.cursor.fetchall()
        ]

    def get_ledger(
        self,
        user_id: str,
        event_type: str,
        unit: str,
        resource: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get ledger entries for an account.

        Args:
            user_id: User ID
            event_type: Event type
            unit: Unit of measurement
            resource: Optional resource identifier
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum entries to return (default 100, max 10000)

        Returns:
            List of ledger entry dicts
        """
        self.cursor.execute(
            """SELECT id, entry_type, amount, balance_after, event_time,
                      reservation_id, reference_id, actor_id, reason, metadata
               FROM meter.get_ledger(%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                user_id,
                event_type,
                unit,
                resource,
                start_time,
                end_time,
                limit,
                self.namespace,
            ),
        )
        return [
            {
                "id": row[0],
                "entry_type": row[1],
                "amount": float(row[2]),
                "balance_after": float(row[3]),
                "event_time": row[4],
                "reservation_id": row[5],
                "reference_id": row[6],
                "actor_id": row[7],
                "reason": row[8],
                "metadata": row[9],
            }
            for row in self.cursor.fetchall()
        ]

    # =========================================================================
    # Periods
    # =========================================================================

    def set_period_config(
        self,
        user_id: str,
        event_type: str,
        unit: str,
        resource: str | None,
        period_start: date,
        period_allocation: float | int | Decimal,
        carry_over_limit: float | int | Decimal | None = None,
    ) -> None:
        """Configure period settings for an account.

        Args:
            user_id: User ID
            event_type: Event type
            unit: Unit of measurement
            resource: Optional resource identifier
            period_start: First day of the period
            period_allocation: Amount granted each period
            carry_over_limit: Max unused to roll forward (None = no limit)
        """
        self.cursor.execute(
            "SELECT meter.set_period_config(%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                event_type,
                unit,
                resource,
                period_start,
                period_allocation,
                carry_over_limit,
                self.namespace,
            ),
        )

    def close_period(
        self,
        user_id: str,
        event_type: str,
        unit: str,
        resource: str | None,
        period_end: date,
    ) -> dict:
        """Close a billing period, handle expiration and carry-over.

        Args:
            user_id: User ID
            event_type: Event type
            unit: Unit of measurement
            resource: Optional resource identifier
            period_end: Last day of the period being closed

        Returns:
            Dict with 'expired', 'carried_over', 'new_balance'
        """
        self.cursor.execute(
            "SELECT expired, carried_over, new_balance FROM meter.close_period(%s, %s, %s, %s, %s, %s)",
            (user_id, event_type, unit, resource, period_end, self.namespace),
        )
        row = self.cursor.fetchone()
        return {
            "expired": float(row[0]),
            "carried_over": float(row[1]),
            "new_balance": float(row[2]),
        }

    def open_period(
        self,
        user_id: str,
        event_type: str,
        unit: str,
        resource: str | None,
        period_start: date,
        allocation: float | int | Decimal | None = None,
    ) -> float:
        """Open a new billing period with allocation.

        Args:
            user_id: User ID
            event_type: Event type
            unit: Unit of measurement
            resource: Optional resource identifier
            period_start: First day of new period
            allocation: Amount to allocate (uses period_allocation if None)

        Returns:
            New balance
        """
        result = self._scalar(
            "SELECT meter.open_period(%s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                event_type,
                unit,
                resource,
                period_start,
                allocation,
                self.namespace,
            ),
        )
        return float(result)

    def release_expired_reservations(self) -> int:
        """Release all expired reservations for this namespace.

        Returns:
            Count of reservations released
        """
        return self._scalar(
            "SELECT meter.release_expired_reservations(%s)", (self.namespace,)
        )

    # =========================================================================
    # Utilities
    # =========================================================================

    def reconcile(self) -> list[dict]:
        """Check for discrepancies between accounts and ledger.

        Returns:
            List of accounts with discrepancies
        """
        self.cursor.execute(
            """SELECT user_id, event_type, resource, unit, account_balance, ledger_sum, discrepancy
               FROM meter.reconcile(%s)""",
            (self.namespace,),
        )
        return [
            {
                "user_id": row[0],
                "event_type": row[1],
                "resource": row[2],
                "unit": row[3],
                "account_balance": float(row[4]),
                "ledger_sum": float(row[5]),
                "discrepancy": float(row[6]),
            }
            for row in self.cursor.fetchall()
        ]

    def get_stats(self) -> dict:
        """Get namespace statistics.

        Returns:
            Dict with counts and totals
        """
        self.cursor.execute(
            """SELECT total_accounts, total_ledger_entries, active_reservations,
                      total_balance, total_reserved
               FROM meter.get_stats(%s)""",
            (self.namespace,),
        )
        row = self.cursor.fetchone()
        return {
            "total_accounts": row[0],
            "total_ledger_entries": row[1],
            "active_reservations": row[2],
            "total_balance": float(row[3]),
            "total_reserved": float(row[4]),
        }

    def get_audit_events(self, *args, **kwargs) -> list[dict]:
        """Not supported - meter module does not have audit events.

        The meter module uses a ledger-based design where all transactions
        are recorded in the ledger table. Use get_ledger() for transaction
        history instead.

        Raises:
            NotImplementedError: Always raised. Use get_ledger() instead.
        """
        raise NotImplementedError(
            "MeterClient does not support audit events. "
            "Use get_ledger() for transaction history."
        )
