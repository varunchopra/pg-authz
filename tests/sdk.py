"""
pg-authz SDK - Python client for the authorization system.

This module provides:
- AuthzClient: SDK-style interface for authorization operations
- Exception classes: AuthzError, AuthzValidationError, AuthzCycleError
- Type aliases: Entity tuple type
"""

from __future__ import annotations

import psycopg


# Type alias for resource/subject tuples
Entity = tuple[str, str]  # (type, id) e.g., ("repo", "payments-api")


# =============================================================================
# EXCEPTIONS
# =============================================================================
# Domain-specific exceptions for better error handling in applications.


class AuthzError(Exception):
    """Base exception for pg-authz operations."""

    pass


class AuthzValidationError(AuthzError):
    """Raised when input validation fails."""

    pass


class AuthzCycleError(AuthzError):
    """Raised when a hierarchy cycle is detected."""

    pass


class AuthzClient:
    """
    SDK-style client for pg-authz.

    This is the interface customers would use. It wraps the SQL functions
    with a Pythonic API using named parameters and tuple-based entities.

    Example:
        authz = AuthzClient(cursor, namespace="production")

        # Grant permission
        authz.grant("admin", resource=("repo", "api"), subject=("team", "eng"))

        # Check permission
        if authz.check("alice", "read", ("repo", "api")):
            allow_access()
    """

    def __init__(self, cursor, namespace: str):
        self.cursor = cursor
        self.namespace = namespace

    def _scalar(self, sql: str, params: tuple):
        """Execute SQL and return single scalar value."""
        try:
            self.cursor.execute(sql, params)
            result = self.cursor.fetchone()
            return result[0] if result else None
        except psycopg.Error as e:
            err_msg = str(e).lower()
            if "cycle" in err_msg:
                raise AuthzCycleError(str(e)) from e
            if "cannot be empty" in err_msg or "exceeds maximum" in err_msg:
                raise AuthzValidationError(str(e)) from e
            raise

    def _fetchall(self, sql: str, params: tuple) -> list:
        """Execute SQL and return all rows."""
        self.cursor.execute(sql, params)
        return self.cursor.fetchall()

    # =========================================================================
    # Core operations
    # =========================================================================

    def grant(
        self,
        permission: str,
        *,
        resource: Entity,
        subject: Entity,
        subject_relation: str | None = None,
    ) -> int:
        """
        Grant a permission on a resource to a subject.

        Args:
            permission: The permission to grant (e.g., "admin", "read")
            resource: The resource as (type, id) tuple (e.g., ("repo", "api"))
            subject: The subject as (type, id) tuple (e.g., ("team", "eng"))
            subject_relation: Optional relation on the subject (e.g., "admin" for team#admin)

        Returns:
            The tuple ID

        Example:
            authz.grant("admin", resource=("repo", "api"), subject=("team", "eng"))
            authz.grant("read", resource=("repo", "api"), subject=("user", "alice"))
            # Grant only to team admins:
            authz.grant("write", resource=("repo", "api"), subject=("team", "eng"), subject_relation="admin")
        """
        resource_type, resource_id = resource
        subject_type, subject_id = subject

        if subject_relation is not None:
            return self._scalar(
                "SELECT authz.write_tuple(%s, %s, %s, %s, %s, %s, %s)",
                (
                    resource_type,
                    resource_id,
                    permission,
                    subject_type,
                    subject_id,
                    subject_relation,
                    self.namespace,
                ),
            )
        else:
            return self._scalar(
                "SELECT authz.write(%s, %s, %s, %s, %s, %s)",
                (
                    resource_type,
                    resource_id,
                    permission,
                    subject_type,
                    subject_id,
                    self.namespace,
                ),
            )

    def revoke(
        self,
        permission: str,
        *,
        resource: Entity,
        subject: Entity,
        subject_relation: str | None = None,
    ) -> bool:
        """
        Revoke a permission on a resource from a subject.

        Args:
            permission: The permission to revoke
            resource: The resource as (type, id) tuple
            subject: The subject as (type, id) tuple
            subject_relation: Optional relation on the subject (e.g., "admin" for team#admin)

        Returns:
            True if a tuple was deleted

        Example:
            authz.revoke("read", resource=("repo", "api"), subject=("user", "alice"))
            # Revoke from team admins only:
            authz.revoke("write", resource=("repo", "api"), subject=("team", "eng"), subject_relation="admin")
        """
        resource_type, resource_id = resource
        subject_type, subject_id = subject

        if subject_relation is not None:
            result = self._scalar(
                "SELECT authz.delete_tuple(%s, %s, %s, %s, %s, %s, %s)",
                (
                    resource_type,
                    resource_id,
                    permission,
                    subject_type,
                    subject_id,
                    subject_relation,
                    self.namespace,
                ),
            )
        else:
            result = self._scalar(
                "SELECT authz.delete(%s, %s, %s, %s, %s, %s)",
                (
                    resource_type,
                    resource_id,
                    permission,
                    subject_type,
                    subject_id,
                    self.namespace,
                ),
            )
        return bool(result)

    def check(self, user_id: str, permission: str, resource: Entity) -> bool:
        """
        Check if a user has a permission on a resource.

        This is the core authorization check - the question every service asks.

        Args:
            user_id: The user ID
            permission: The permission to check (e.g., "read", "write")
            resource: The resource as (type, id) tuple

        Returns:
            True if the user has the permission

        Example:
            if authz.check("alice", "read", ("repo", "api")):
                return repo_contents
        """
        resource_type, resource_id = resource
        return self._scalar(
            "SELECT authz.check(%s, %s, %s, %s, %s)",
            (user_id, permission, resource_type, resource_id, self.namespace),
        )

    def check_any(self, user_id: str, permissions: list[str], resource: Entity) -> bool:
        """
        Check if a user has any of the specified permissions.

        Useful for "can edit OR admin" style checks. More efficient than
        multiple check() calls.

        Args:
            user_id: The user ID
            permissions: List of permissions (user needs at least one)
            resource: The resource as (type, id) tuple

        Returns:
            True if the user has at least one of the permissions
        """
        resource_type, resource_id = resource
        return self._scalar(
            "SELECT authz.check_any(%s, %s, %s, %s, %s)",
            (user_id, permissions, resource_type, resource_id, self.namespace),
        )

    def check_all(self, user_id: str, permissions: list[str], resource: Entity) -> bool:
        """
        Check if a user has all of the specified permissions.

        Useful for operations requiring multiple permissions.

        Args:
            user_id: The user ID
            permissions: List of permissions (user needs all of them)
            resource: The resource as (type, id) tuple

        Returns:
            True if the user has all of the permissions
        """
        resource_type, resource_id = resource
        return self._scalar(
            "SELECT authz.check_all(%s, %s, %s, %s, %s)",
            (user_id, permissions, resource_type, resource_id, self.namespace),
        )

    # =========================================================================
    # Audit and listing
    # =========================================================================

    def explain(self, user_id: str, permission: str, resource: Entity) -> list[str]:
        """
        Explain why a user has a permission.

        Returns the permission paths - useful for debugging and auditing.

        Args:
            user_id: The user ID
            permission: The permission to explain
            resource: The resource as (type, id) tuple

        Returns:
            List of human-readable explanation strings

        Example:
            paths = authz.explain("alice", "read", ("repo", "api"))
            # ["HIERARCHY: alice is member of team:eng which has admin (admin -> read)"]
        """
        resource_type, resource_id = resource
        rows = self._fetchall(
            "SELECT * FROM authz.explain_text(%s, %s, %s, %s, %s)",
            (user_id, permission, resource_type, resource_id, self.namespace),
        )
        return [row[0] for row in rows]

    def list_users(
        self,
        permission: str,
        resource: Entity,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> list[str]:
        """
        List users who have a permission on a resource.

        Args:
            permission: The permission to check
            resource: The resource as (type, id) tuple
            limit: Maximum number of results (optional)
            cursor: Pagination cursor (optional)

        Returns:
            List of user IDs

        Example:
            users = authz.list_users("read", ("repo", "api"))
            # ["alice", "bob", "charlie"]
        """
        resource_type, resource_id = resource
        if limit is not None:
            rows = self._fetchall(
                "SELECT * FROM authz.list_users(%s, %s, %s, %s, %s, %s)",
                (resource_type, resource_id, permission, self.namespace, limit, cursor),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM authz.list_users(%s, %s, %s, %s)",
                (resource_type, resource_id, permission, self.namespace),
            )
        return [row[0] for row in rows]

    def list_resources(
        self,
        user_id: str,
        resource_type: str,
        permission: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> list[str]:
        """
        List resources a user has a permission on.

        Args:
            user_id: The user ID
            resource_type: The resource type to list
            permission: The permission to check
            limit: Maximum number of results (optional)
            cursor: Pagination cursor (optional)

        Returns:
            List of resource IDs

        Example:
            repos = authz.list_resources("alice", "repo", "read")
            # ["api", "frontend", "docs"]
        """
        if limit is not None:
            rows = self._fetchall(
                "SELECT * FROM authz.list_resources(%s, %s, %s, %s, %s, %s)",
                (user_id, resource_type, permission, self.namespace, limit, cursor),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM authz.list_resources(%s, %s, %s, %s)",
                (user_id, resource_type, permission, self.namespace),
            )
        return [row[0] for row in rows]

    def filter_authorized(
        self, user_id: str, resource_type: str, permission: str, resource_ids: list[str]
    ) -> list[str]:
        """Filter resource IDs to only those the user can access."""
        rows = self._fetchall(
            "SELECT unnest(authz.filter_authorized(%s, %s, %s, %s, %s))",
            (user_id, resource_type, permission, resource_ids, self.namespace),
        )
        return [row[0] for row in rows]

    # =========================================================================
    # Setup helpers
    # =========================================================================

    def set_hierarchy(self, resource_type: str, *permissions: str):
        """
        Define permission hierarchy for a resource type.

        Each permission implies the next in the chain.

        Args:
            resource_type: The resource type (e.g., "repo")
            *permissions: Permissions in order of power (e.g., "admin", "write", "read")

        Example:
            authz.set_hierarchy("repo", "admin", "write", "read")
            # Now admin implies write, write implies read
        """
        for i in range(len(permissions) - 1):
            self.cursor.execute(
                "SELECT authz.add_hierarchy(%s, %s, %s, %s)",
                (resource_type, permissions[i], permissions[i + 1], self.namespace),
            )

    def add_hierarchy_rule(self, resource_type: str, permission: str, implies: str):
        """
        Add a single hierarchy rule (for complex/branching hierarchies).

        Args:
            resource_type: The resource type
            permission: The higher permission
            implies: The permission it implies

        Example:
            authz.add_hierarchy_rule("doc", "admin", "read")
            authz.add_hierarchy_rule("doc", "admin", "share")
        """
        self._scalar(
            "SELECT authz.add_hierarchy(%s, %s, %s, %s)",
            (resource_type, permission, implies, self.namespace),
        )

    def remove_hierarchy_rule(self, resource_type: str, permission: str, implies: str):
        """Remove a single hierarchy rule."""
        self._scalar(
            "SELECT authz.remove_hierarchy(%s, %s, %s, %s)",
            (resource_type, permission, implies, self.namespace),
        )

    def clear_hierarchy(self, resource_type: str) -> int:
        """Clear all hierarchy rules for a resource type."""
        return self._scalar(
            "SELECT authz.clear_hierarchy(%s, %s)",
            (resource_type, self.namespace),
        )

    # =========================================================================
    # Admin/maintenance operations
    # =========================================================================

    def verify(self) -> list[dict]:
        """
        Check computed table consistency.

        Returns list of discrepancies (empty if healthy).

        Example:
            issues = authz.verify()
            if issues:
                authz.repair()
        """
        rows = self._fetchall(
            "SELECT resource_type, resource_id, status, details FROM authz.verify_computed(%s)",
            (self.namespace,),
        )
        return [
            {
                "resource_type": r[0],
                "resource_id": r[1],
                "status": r[2],
                "details": r[3],
            }
            for r in rows
        ]

    def repair(self) -> int:
        """
        Rebuild computed permissions from tuples.

        Returns count of permissions recomputed.

        Example:
            count = authz.repair()
            print(f"Rebuilt {count} permissions")
        """
        return self._scalar("SELECT authz.repair_computed(%s)", (self.namespace,))

    def stats(self) -> dict:
        """
        Get namespace statistics for monitoring.

        Returns:
            Dictionary with:
            - tuple_count: Number of relationship tuples
            - computed_count: Number of pre-computed permissions
            - hierarchy_rule_count: Number of hierarchy rules
            - amplification_factor: computed_count / tuple_count
            - unique_users: Distinct users with permissions
            - unique_resources: Distinct resources with permissions

        Example:
            stats = authz.stats()
            if stats['amplification_factor'] > 100:
                print("Warning: High write amplification")
        """
        self.cursor.execute("SELECT * FROM authz.get_stats(%s)", (self.namespace,))
        row = self.cursor.fetchone()
        if row:
            return {
                "tuple_count": row[0],
                "computed_count": row[1],
                "hierarchy_rule_count": row[2],
                "amplification_factor": float(row[3]) if row[3] else None,
                "unique_users": row[4],
                "unique_resources": row[5],
            }
        return {}

    def disable_triggers(self):
        """Disable recompute triggers for bulk operations."""
        self.cursor.execute("SELECT authz.disable_recompute_triggers()")

    def enable_triggers(self):
        """Re-enable recompute triggers after bulk operations."""
        self.cursor.execute("SELECT authz.enable_recompute_triggers()")

    def recompute_all(self) -> int:
        """Manually trigger full recompute. Use after bulk imports."""
        return self._scalar("SELECT authz.recompute_all(%s)", (self.namespace,))

    def bulk_grant(
        self, permission: str, *, resource: Entity, subject_ids: list[str]
    ) -> int:
        """
        Grant permission to many users at once (single statement).

        Returns count of tuples inserted.

        Example:
            authz.bulk_grant("read", resource=("doc", "1"), subject_ids=["alice", "bob", "carol"])
        """
        resource_type, resource_id = resource
        return self._scalar(
            "SELECT authz.write_tuples_bulk(%s, %s, %s, 'user', %s, %s)",
            (resource_type, resource_id, permission, subject_ids, self.namespace),
        )

    def bulk_grant_resources(
        self,
        permission: str,
        *,
        resource_type: str,
        resource_ids: list[str],
        subject: Entity,
        subject_relation: str | None = None,
    ) -> int:
        """
        Grant permission to a subject on many resources at once.

        Optimized for bulk operations: uses single recompute instead of
        per-resource triggers.

        Returns count of tuples inserted.

        Example:
            authz.bulk_grant_resources(
                "read",
                resource_type="doc",
                resource_ids=["doc-1", "doc-2", "doc-3"],
                subject=("team", "engineering"),
            )
        """
        subject_type, subject_id = subject
        return self._scalar(
            "SELECT authz.grant_to_resources_bulk(%s, %s, %s, %s, %s, %s, %s)",
            (
                resource_type,
                resource_ids,
                permission,
                subject_type,
                subject_id,
                subject_relation,
                self.namespace,
            ),
        )


# =============================================================================
# Test helpers - for internal testing only
# =============================================================================


class AuthzTestHelpers:
    """
    Test helper methods for simulating corruption and direct table access.

    These methods bypass the normal API to simulate edge cases.
    Not part of the public API.
    """

    def __init__(self, cursor, namespace: str):
        self.cursor = cursor
        self.namespace = namespace

    def delete_computed(self, resource: Entity):
        """Delete all computed entries for a resource (simulates corruption)."""
        resource_type, resource_id = resource
        self.cursor.execute(
            """
            DELETE FROM authz.computed
            WHERE namespace = %s AND resource_type = %s AND resource_id = %s
        """,
            (self.namespace, resource_type, resource_id),
        )

    def insert_computed(self, permission: str, resource: Entity, user_id: str):
        """Insert a spurious computed entry (simulates corruption)."""
        resource_type, resource_id = resource
        self.cursor.execute(
            """
            INSERT INTO authz.computed
            (namespace, resource_type, resource_id, permission, user_id)
            VALUES (%s, %s, %s, %s, %s)
        """,
            (self.namespace, resource_type, resource_id, permission, user_id),
        )

    def delete_tuples(self, resource: Entity):
        """Delete tuples without triggering recompute (simulates orphaned computed)."""
        resource_type, resource_id = resource
        self.cursor.execute("SELECT authz.disable_recompute_triggers()")
        try:
            self.cursor.execute(
                """
                DELETE FROM authz.tuples
                WHERE namespace = %s AND resource_type = %s AND resource_id = %s
            """,
                (self.namespace, resource_type, resource_id),
            )
        finally:
            self.cursor.execute("SELECT authz.enable_recompute_triggers()")

    def count_computed(
        self,
        resource: Entity | None = None,
        permission: str | None = None,
        user_id: str | None = None,
    ) -> int:
        """Count computed entries (for testing deduplication)."""
        conditions = ["namespace = %s"]
        params: list = [self.namespace]

        if resource:
            conditions.append("resource_type = %s")
            conditions.append("resource_id = %s")
            params.extend(resource)
        if permission:
            conditions.append("permission = %s")
            params.append(permission)
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)

        sql = f"SELECT COUNT(*) FROM authz.computed WHERE {' AND '.join(conditions)}"
        self.cursor.execute(sql, tuple(params))
        result = self.cursor.fetchone()
        return result[0] if result else 0
