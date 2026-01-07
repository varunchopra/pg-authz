"""Pytest fixtures for postkit.meter tests."""

from pathlib import Path

import psycopg
import pytest
from postkit.meter import MeterClient
from tests.conftest import DATABASE_URL
from tests.meter.helpers import MeterTestHelpers


@pytest.fixture(scope="session")
def db_connection():
    """
    Session-scoped database connection.
    Installs the meter schema once at the start of the test session.
    """
    conn = psycopg.connect(DATABASE_URL, autocommit=True)

    # Install fresh schema
    conn.execute("DROP SCHEMA IF EXISTS meter CASCADE")

    # Load the built SQL file (sdk/tests/meter/ -> root/dist/)
    dist_sql = Path(__file__).parent.parent.parent.parent / "dist" / "meter.sql"
    if not dist_sql.exists():
        pytest.fail("dist/meter.sql not found. Run 'make build' first.")

    conn.execute(dist_sql.read_text())

    yield conn

    # Cleanup at end of session
    conn.execute("DROP SCHEMA IF EXISTS meter CASCADE")
    conn.close()


def _make_namespace(request) -> str:
    """Generate a unique namespace from test name."""
    namespace = request.node.name.replace("[", "_").replace("]", "_").replace("-", "_")
    return "t_" + namespace.lower()[:50]


def _cleanup(cursor, namespace: str):
    """Clean up all data for a namespace."""
    cursor.execute("DELETE FROM meter.reservations WHERE namespace = %s", (namespace,))
    # Disable immutability trigger for cleanup, then re-enable
    cursor.execute("ALTER TABLE meter.ledger DISABLE TRIGGER ledger_no_delete")
    cursor.execute("DELETE FROM meter.ledger WHERE namespace = %s", (namespace,))
    cursor.execute("ALTER TABLE meter.ledger ENABLE TRIGGER ledger_no_delete")
    cursor.execute("DELETE FROM meter.accounts WHERE namespace = %s", (namespace,))


@pytest.fixture
def meter(db_connection, request):
    """
    SDK-style MeterClient for tests.

    Each test gets its own namespace for isolation.
    Cleanup is automatic after each test.

    Example:
        def test_allocate_consume(meter):
            meter.allocate("alice", "llm_call", 1000, "tokens")
            result = meter.consume("alice", "llm_call", 100, "tokens")
            assert result["success"] is True
    """
    namespace = _make_namespace(request)
    cursor = db_connection.cursor()
    client = MeterClient(cursor, namespace)

    yield client

    _cleanup(cursor, namespace)
    cursor.close()


@pytest.fixture
def test_helpers(db_connection, request):
    """
    Test helper utilities for direct table access.

    Example:
        def test_ledger_entries(meter, test_helpers):
            meter.allocate("alice", "llm_call", 1000, "tokens")
            assert test_helpers.count_ledger_entries() == 1
    """
    namespace = _make_namespace(request)
    cursor = db_connection.cursor()
    helpers = MeterTestHelpers(cursor, namespace)

    yield helpers

    cursor.close()


@pytest.fixture
def make_meter(db_connection):
    """
    Factory fixture that creates MeterClients and tracks namespaces for cleanup.

    Use this when tests need multiple namespaces. Cleanup happens automatically
    even if the test fails mid-execution.

    Example:
        def test_isolation(make_meter):
            tenant_a = make_meter("tenant_a")
            tenant_b = make_meter("tenant_b")
            # ... test code, no manual cleanup needed
    """
    created = []
    cursor = db_connection.cursor()

    def _make(namespace: str) -> MeterClient:
        created.append(namespace)
        return MeterClient(cursor, namespace)

    yield _make

    # Cleanup all created namespaces (runs even if test fails)
    for ns in created:
        _cleanup(cursor, ns)
    cursor.close()
