"""
Maintenance and operational tests for pg-authz.

Tests for:
- VACUUM behavior
- pg_dump/pg_restore compatibility
- verify/repair operations
- Bulk operations
"""

import os
import subprocess
import pytest
import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/postgres"
)


class TestVacuumBehavior:
    """Test that VACUUM doesn't break authorization."""

    def test_vacuum_preserves_permissions(self, authz):
        """VACUUM should not affect computed permissions."""
        # Setup permissions
        authz.set_hierarchy("doc", "admin", "write", "read")
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))
        authz.grant("admin", resource=("doc", "1"), subject=("team", "eng"))

        # Verify initial state
        assert authz.check("alice", "read", ("doc", "1"))

        # Run VACUUM
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cursor = conn.cursor()
        cursor.execute("VACUUM authz.tuples")
        cursor.execute("VACUUM authz.computed")
        cursor.execute("VACUUM authz.permission_hierarchy")
        conn.close()

        # Permissions should still work
        assert authz.check("alice", "read", ("doc", "1"))

    def test_vacuum_full_preserves_permissions(self, authz):
        """VACUUM FULL should not affect computed permissions."""
        # Setup permissions
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("write", resource=("doc", "2"), subject=("user", "bob"))

        # Verify initial state
        assert authz.check("alice", "read", ("doc", "1"))
        assert authz.check("bob", "write", ("doc", "2"))

        # Run VACUUM FULL (requires exclusive lock)
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cursor = conn.cursor()
        cursor.execute("VACUUM FULL authz.tuples")
        cursor.execute("VACUUM FULL authz.computed")
        conn.close()

        # Permissions should still work
        assert authz.check("alice", "read", ("doc", "1"))
        assert authz.check("bob", "write", ("doc", "2"))


class TestVerifyRepair:
    """Test verify and repair operations."""

    def test_verify_clean_state(self, authz):
        """verify() on clean state returns no issues."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "bob"))
        authz.grant("write", resource=("doc", "2"), subject=("team", "eng"))

        issues = authz.verify()
        assert len(issues) == 0

    def test_repair_fixes_inconsistencies(self, authz, db_connection):
        """repair() fixes any inconsistencies in computed table."""
        # Setup permissions normally
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        # Manually corrupt the computed table (simulate a bug/crash)
        cursor = db_connection.cursor()
        cursor.execute(
            "DELETE FROM authz.computed WHERE namespace = %s", (authz.namespace,)
        )

        # Verify detects the problem
        issues = authz.verify()
        assert len(issues) > 0, "Should detect missing computed entry"

        # Repair fixes it
        authz.repair()

        # Verify clean now
        issues = authz.verify()
        assert len(issues) == 0

        # Permission works again
        assert authz.check("alice", "read", ("doc", "1"))


class TestBackupRestore:
    """Test pg_dump/pg_restore compatibility.

    Runs pg_dump inside the Docker container to avoid version mismatch issues
    between host pg_dump and server version.
    """

    PG_CONTAINER = os.environ.get("PG_CONTAINER", "pg-authz-test")

    @pytest.fixture
    def check_docker_container(self):
        """Check if the test container is running."""
        result = subprocess.run(
            ["docker", "inspect", self.PG_CONTAINER],
            capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip(f"Docker container {self.PG_CONTAINER} not running")
        return True

    def test_dump_schema_succeeds(self, authz, check_docker_container):
        """pg_dump of authz schema should succeed."""
        # Setup some data
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        # Run pg_dump inside the container (avoids version mismatch)
        result = subprocess.run(
            [
                "docker",
                "exec",
                self.PG_CONTAINER,
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-n",
                "authz",
                "--no-owner",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"pg_dump failed: {result.stderr}"
        assert "CREATE TABLE authz.tuples" in result.stdout
        assert "CREATE TABLE authz.computed" in result.stdout


class TestBulkOperations:
    """Bulk import functionality."""

    def test_disable_enable_triggers(self, authz):
        """Can disable and re-enable triggers for bulk imports."""
        authz.disable_triggers()
        authz.bulk_grant("read", resource=("doc", "bulk-1"), subject_ids=["alice"])

        # Should NOT be in computed yet
        assert not authz.check("alice", "read", ("doc", "bulk-1"))

        authz.enable_triggers()
        authz.recompute_all()

        # NOW it should be there
        assert authz.check("alice", "read", ("doc", "bulk-1"))

    def test_bulk_grant_many_users(self, authz):
        """bulk_grant handles many users efficiently."""
        users = [f"user-{i}" for i in range(100)]
        authz.bulk_grant("read", resource=("doc", "1"), subject_ids=users)

        for user in users:
            assert authz.check(user, "read", ("doc", "1"))
