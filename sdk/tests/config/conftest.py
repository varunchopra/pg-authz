"""Pytest fixtures for postkit.config tests."""

from pathlib import Path

import psycopg
import pytest
from postkit.config import ConfigClient

from tests.config.helpers import ConfigTestHelpers
from tests.conftest import DATABASE_URL


@pytest.fixture(scope="session")
def db_connection():
    """
    Session-scoped database connection.
    Installs the config schema once at the start of the test session.
    """
    conn = psycopg.connect(DATABASE_URL, autocommit=True)

    # Install fresh schema
    conn.execute("DROP SCHEMA IF EXISTS config CASCADE")

    # Load the built SQL file (sdk/tests/config/ -> root/dist/)
    dist_sql = Path(__file__).parent.parent.parent.parent / "dist" / "config.sql"
    if not dist_sql.exists():
        pytest.fail("dist/config.sql not found. Run 'make build' first.")

    conn.execute(dist_sql.read_text())

    yield conn

    # Cleanup at end of session
    conn.execute("DROP SCHEMA IF EXISTS config CASCADE")
    conn.close()


def _make_namespace(request) -> str:
    """Generate a unique namespace from test name."""
    namespace = request.node.name.replace("[", "_").replace("]", "_").replace("-", "_")
    return "t_" + namespace.lower()[:50]


def _cleanup(cursor, namespace: str):
    """Clean up all data for a namespace."""
    cursor.execute("DELETE FROM config.audit_events WHERE namespace = %s", (namespace,))
    cursor.execute("DELETE FROM config.entries WHERE namespace = %s", (namespace,))
    cursor.execute(
        "DELETE FROM config.version_counters WHERE namespace = %s", (namespace,)
    )


@pytest.fixture
def config(db_connection, request):
    """
    SDK-style ConfigClient for tests.

    Each test gets its own namespace for isolation.
    Cleanup is automatic after each test.

    Example:
        def test_set_get(config):
            config.set("prompts/bot", {"template": "Hello"})
            result = config.get("prompts/bot")
            assert result["value"]["template"] == "Hello"
    """
    namespace = _make_namespace(request)
    cursor = db_connection.cursor()
    client = ConfigClient(cursor, namespace)

    yield client

    _cleanup(cursor, namespace)
    cursor.close()


@pytest.fixture
def test_helpers(db_connection, request):
    """
    Test helper utilities for direct table access.

    Example:
        def test_version_count(config, test_helpers):
            config.set("prompts/bot", {"v": 1})
            config.set("prompts/bot", {"v": 2})
            assert test_helpers.count_versions("prompts/bot") == 2
    """
    namespace = _make_namespace(request)
    cursor = db_connection.cursor()
    helpers = ConfigTestHelpers(cursor, namespace)

    yield helpers

    cursor.close()


@pytest.fixture
def make_config(db_connection):
    """
    Factory fixture that creates ConfigClients and tracks namespaces for cleanup.

    Use this when tests need multiple namespaces. Cleanup happens automatically
    even if the test fails mid-execution.

    Example:
        def test_isolation(make_config):
            tenant_a = make_config("tenant_a")
            tenant_b = make_config("tenant_b")
            # ... test code, no manual cleanup needed
    """
    created = []
    cursor = db_connection.cursor()

    def _make(namespace: str) -> ConfigClient:
        created.append(namespace)
        return ConfigClient(cursor, namespace)

    yield _make

    # Cleanup all created namespaces (runs even if test fails)
    for ns in created:
        _cleanup(cursor, ns)
    cursor.close()
