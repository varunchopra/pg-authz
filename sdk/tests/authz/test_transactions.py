"""
Transaction semantics tests for postkit/authz.

Tests for:
- Rollback behavior
- Atomicity of multiple writes
- Visibility guarantees
"""

import os
import pytest
import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/postgres"
)


class TestTransactionSemantics:
    """Verify transactional behavior."""

    def test_rollback_reverts_permission(self, make_authz):
        """Rolled-back grants should not persist."""
        # Use make_authz to ensure cleanup even if test fails
        checker = make_authz("test_rollback")

        # Start transaction, grant, then rollback
        conn = psycopg.connect(DATABASE_URL, autocommit=False)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT authz.write('doc', '1', 'read', 'user', 'alice', 'test_rollback')"
        )
        conn.rollback()
        conn.close()

        # Verify not persisted
        assert not checker.check("alice", "read", ("doc", "1"))

    def test_multiple_writes_atomic(self, make_authz):
        """Multiple writes in one transaction are atomic."""
        checker = make_authz("test_atomic")

        conn = psycopg.connect(DATABASE_URL, autocommit=False)
        cursor = conn.cursor()

        # Two writes in same transaction
        cursor.execute(
            "SELECT authz.write('team', 'eng', 'member', 'user', 'alice', 'test_atomic')"
        )
        cursor.execute(
            "SELECT authz.write('doc', '1', 'read', 'team', 'eng', 'test_atomic')"
        )

        # Before commit: check in same transaction should see it
        cursor.execute("SELECT authz.check('alice', 'read', 'doc', '1', 'test_atomic')")
        assert cursor.fetchone()[0] is True

        conn.commit()
        conn.close()

        # After commit: visible to other connections
        assert checker.check("alice", "read", ("doc", "1"))

    def test_partial_rollback_not_visible(self, make_authz):
        """Partially rolled-back transaction doesn't leave partial state."""
        checker = make_authz("test_partial")

        conn = psycopg.connect(DATABASE_URL, autocommit=False)
        cursor = conn.cursor()

        # First write succeeds
        cursor.execute(
            "SELECT authz.write('doc', '1', 'read', 'user', 'alice', 'test_partial')"
        )

        # Force an error (invalid identifier)
        try:
            cursor.execute(
                "SELECT authz.write('doc', '2', 'read', 'user', '', 'test_partial')"
            )
        except psycopg.Error:
            conn.rollback()

        conn.close()

        # Neither write should be visible
        assert not checker.check("alice", "read", ("doc", "1"))
