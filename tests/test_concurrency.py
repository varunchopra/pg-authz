"""
Concurrency tests for pg-authz.

pg-authz serializes writes within each namespace to guarantee the computed
table is always correct. Different namespaces can write in parallel.
"""

import os
import pytest
import psycopg
import threading
import time

from sdk import AuthzTestHelpers

# Database connection from environment or default (matches Makefile)
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/postgres"
)


class TestWriteSerialization:
    """Verify writes are serialized within namespace for correctness."""

    def test_concurrent_writes_always_correct(self, db_connection):
        """
        Concurrent writes to the same namespace are serialized.
        This guarantees the computed table is always correct.

        Scenario:
        T1: Add Alice to team:eng
        T2: Add team:eng as admin on repo:api

        Result: Alice MUST have admin on repo:api (no race condition possible)
        """
        namespace = "test_serialized_writes"

        cursor = db_connection.cursor()
        cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (namespace,))
        cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (namespace,))

        results = {"t1_done": False, "t2_done": False, "errors": []}
        barrier = threading.Barrier(2)

        def transaction_1():
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                cur.execute(
                    "SELECT authz.write('team', 'eng', 'member', 'user', 'alice', %s)",
                    (namespace,),
                )
                conn.commit()
                results["t1_done"] = True
                conn.close()
            except Exception as e:
                results["errors"].append(f"T1: {e}")

        def transaction_2():
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                cur.execute(
                    "SELECT authz.write('repo', 'api', 'admin', 'team', 'eng', %s)",
                    (namespace,),
                )
                conn.commit()
                results["t2_done"] = True
                conn.close()
            except Exception as e:
                results["errors"].append(f"T2: {e}")

        t1 = threading.Thread(target=transaction_1)
        t2 = threading.Thread(target=transaction_2)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not results["errors"], f"Errors: {results['errors']}"
        assert results["t1_done"] and results["t2_done"]

        # The critical assertion: Alice MUST have access
        # With serialization, this is guaranteed regardless of timing
        cursor.execute(
            "SELECT authz.check('alice', 'admin', 'repo', 'api', %s)", (namespace,)
        )
        has_permission = cursor.fetchone()[0]
        assert has_permission, "Alice MUST have admin on repo:api via team:eng"

        # verify() should show no issues
        cursor.execute("SELECT COUNT(*) FROM authz.verify_computed(%s)", (namespace,))
        issues = cursor.fetchone()[0]
        assert issues == 0, "Computed table should be consistent"

        # Cleanup
        cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (namespace,))
        cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (namespace,))

    def test_concurrent_same_resource_all_succeed(self, db_connection):
        """Multiple concurrent grants to the same resource should all succeed."""
        namespace = "test_concurrent_same_resource"

        cursor = db_connection.cursor()
        cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (namespace,))
        cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (namespace,))

        num_users = 10
        results = {"completed": 0, "errors": []}
        results_lock = threading.Lock()
        barrier = threading.Barrier(num_users)

        def grant_to_user(user_id):
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                cur.execute(
                    "SELECT authz.write('doc', 'shared', 'read', 'user', %s, %s)",
                    (user_id, namespace),
                )
                conn.commit()
                with results_lock:
                    results["completed"] += 1
                conn.close()
            except Exception as e:
                with results_lock:
                    results["errors"].append(f"User {user_id}: {e}")

        threads = [
            threading.Thread(target=grant_to_user, args=(f"user-{i}",))
            for i in range(num_users)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not results["errors"], f"Errors: {results['errors']}"
        assert results["completed"] == num_users

        # All users should have read permission
        for i in range(num_users):
            cursor.execute(
                "SELECT authz.check(%s, 'read', 'doc', 'shared', %s)",
                (f"user-{i}", namespace),
            )
            assert cursor.fetchone()[0], f"user-{i} should have read permission"

        # Cleanup
        cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (namespace,))
        cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (namespace,))


class TestNamespaceIsolation:
    """Verify different namespaces can write in parallel."""

    def test_different_namespaces_not_blocked(self, db_connection):
        """Writes to different namespaces proceed in parallel."""
        ns1 = "test_parallel_ns1"
        ns2 = "test_parallel_ns2"

        cursor = db_connection.cursor()
        for ns in [ns1, ns2]:
            cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (ns,))
            cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (ns,))

        results = {"start_times": {}, "end_times": {}, "errors": []}
        barrier = threading.Barrier(2)

        def write_to_namespace(ns, thread_id):
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                results["start_times"][thread_id] = time.time()
                cur.execute(
                    "SELECT authz.write('doc', '1', 'read', 'user', 'alice', %s)",
                    (ns,),
                )
                # Simulate some work to make overlap measurable
                cur.execute("SELECT pg_sleep(0.05)")
                conn.commit()
                results["end_times"][thread_id] = time.time()
                conn.close()
            except Exception as e:
                results["errors"].append(f"{thread_id}: {e}")

        t1 = threading.Thread(target=write_to_namespace, args=(ns1, "T1"))
        t2 = threading.Thread(target=write_to_namespace, args=(ns2, "T2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not results["errors"], f"Errors: {results['errors']}"

        # Both should have overlapping execution (parallel, not serialized)
        t1_start = results["start_times"]["T1"]
        t1_end = results["end_times"]["T1"]
        t2_start = results["start_times"]["T2"]
        t2_end = results["end_times"]["T2"]

        # Check for overlap: T1 started before T2 ended AND T2 started before T1 ended
        overlapped = (t1_start < t2_end) and (t2_start < t1_end)
        assert overlapped, "Different namespaces should execute in parallel"

        # Cleanup
        for ns in [ns1, ns2]:
            cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (ns,))
            cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (ns,))


class TestAdvisoryLockBehavior:
    """Verify advisory lock serialization behavior."""

    def test_advisory_lock_serializes_same_resource(self, db_connection):
        """Concurrent recomputes of the same resource are serialized."""
        namespace = "test_advisory_lock"

        cursor = db_connection.cursor()
        cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (namespace,))
        cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (namespace,))

        # Setup: create a resource with some permissions
        cursor.execute(
            "SELECT authz.write('doc', '1', 'read', 'user', 'alice', %s)",
            (namespace,),
        )

        results = {"completed": 0, "errors": []}
        results_lock = threading.Lock()
        barrier = threading.Barrier(3)

        def force_recompute(thread_id):
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                cur.execute(
                    "SELECT authz.recompute_resource('doc', '1', %s)", (namespace,)
                )
                conn.commit()
                with results_lock:
                    results["completed"] += 1
                conn.close()
            except Exception as e:
                with results_lock:
                    results["errors"].append(f"Thread {thread_id}: {e}")

        threads = [
            threading.Thread(target=force_recompute, args=(i,)) for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not results["errors"], f"Errors: {results['errors']}"
        assert results["completed"] == 3

        # Permission should still be correct
        cursor.execute(
            "SELECT authz.check('alice', 'read', 'doc', '1', %s)", (namespace,)
        )
        assert cursor.fetchone()[0]

        # Cleanup
        cursor.execute("DELETE FROM authz.tuples WHERE namespace = %s", (namespace,))
        cursor.execute("DELETE FROM authz.computed WHERE namespace = %s", (namespace,))


class TestConcurrentHierarchyChanges:
    """Test hierarchy changes concurrent with tuple writes."""

    def test_hierarchy_change_during_writes(self, make_authz):
        """Hierarchy change while writes are happening stays consistent."""
        namespace = "test_concurrent_hierarchy"
        checker = make_authz(namespace)

        results = {"errors": []}
        results_lock = threading.Lock()
        barrier = threading.Barrier(3)

        def write_tuples(thread_id):
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                for i in range(20):
                    cur.execute(
                        "SELECT authz.write('doc', %s, 'admin', 'user', 'alice', %s)",
                        (f"doc-{thread_id}-{i}", namespace),
                    )
                    conn.commit()
                conn.close()
            except Exception as e:
                with results_lock:
                    results["errors"].append(f"writer-{thread_id}: {e}")

        def modify_hierarchy():
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                # Add, then remove, then add again
                for _ in range(3):
                    cur.execute(
                        "SELECT authz.add_hierarchy('doc', 'admin', 'read', %s)",
                        (namespace,),
                    )
                    conn.commit()
                    time.sleep(0.01)
                    cur.execute(
                        "SELECT authz.remove_hierarchy('doc', 'admin', 'read', %s)",
                        (namespace,),
                    )
                    conn.commit()
                conn.close()
            except Exception as e:
                with results_lock:
                    results["errors"].append(f"hierarchy: {e}")

        threads = [
            threading.Thread(target=write_tuples, args=(1,)),
            threading.Thread(target=write_tuples, args=(2,)),
            threading.Thread(target=modify_hierarchy),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not results["errors"], f"Errors: {results['errors']}"

        # Verify consistency
        issues = checker.verify()
        assert len(issues) == 0, "Computed table must be consistent"


class TestConcurrentIdempotency:
    """Test idempotency under concurrent access."""

    def test_concurrent_identical_grants_idempotent(self, make_authz, db_connection):
        """Multiple concurrent identical grants don't create duplicates."""
        namespace = "test_idempotent"
        checker = make_authz(namespace)
        helpers = AuthzTestHelpers(db_connection.cursor(), namespace)

        results = {"ids": [], "errors": []}
        barrier = threading.Barrier(5)
        lock = threading.Lock()

        def grant_same_permission(thread_id):
            try:
                conn = psycopg.connect(DATABASE_URL)
                cur = conn.cursor()
                barrier.wait()
                cur.execute(
                    "SELECT authz.write('doc', '1', 'read', 'user', 'alice', %s)",
                    (namespace,),
                )
                tuple_id = cur.fetchone()[0]
                conn.commit()
                with lock:
                    results["ids"].append(tuple_id)
                conn.close()
            except Exception as e:
                with lock:
                    results["errors"].append(str(e))

        threads = [
            threading.Thread(target=grant_same_permission, args=(i,)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not results["errors"], f"Errors: {results['errors']}"
        # All threads should get the same tuple ID (idempotent)
        assert len(set(results["ids"])) == 1, "All grants should return same ID"

        # Only one computed entry should exist
        assert (
            helpers.count_computed(
                resource=("doc", "1"), permission="read", user_id="alice"
            )
            == 1
        )
