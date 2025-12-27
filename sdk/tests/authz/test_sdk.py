"""
SDK core behavior tests for postkit/authz.

Tests the AuthzClient SDK through its public API - the "happy path" tests.
Edge cases and specialized functionality are in dedicated test files.
"""

import pytest


class TestGrantAndCheck:
    """Core grant/check behavior."""

    def test_grant_allows_access(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check("alice", "read", ("doc", "1"))

    def test_no_grant_means_no_access(self, authz):
        assert not authz.check("alice", "read", ("doc", "1"))

    def test_grant_is_idempotent(self, authz):
        id1 = authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        id2 = authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert id1 == id2

    def test_different_permissions_are_independent(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check("alice", "read", ("doc", "1"))
        assert not authz.check("alice", "write", ("doc", "1"))


class TestRevoke:
    """Revocation behavior."""

    def test_revoke_removes_access(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        assert authz.check("alice", "read", ("doc", "1"))

        authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        assert not authz.check("alice", "read", ("doc", "1"))

    def test_revoke_group_membership(self, authz):
        authz.grant("write", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "bob"))
        assert authz.check("bob", "write", ("doc", "1"))

        authz.revoke("member", resource=("team", "eng"), subject=("user", "bob"))
        assert not authz.check("bob", "write", ("doc", "1"))

    def test_revoke_direct_keeps_group_access(self, authz):
        # Alice has access via team AND direct grant
        authz.grant("read", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        # Revoke direct grant
        authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))

        # Still has access via team
        assert authz.check("alice", "read", ("doc", "1"))

    def test_revoke_nonexistent_returns_false(self, authz):
        """Revoking a permission that doesn't exist returns False."""
        result = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        assert result is False

    def test_revoke_existing_returns_true(self, authz):
        """Revoking an existing permission returns True."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        result = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        assert result is True

    def test_double_revoke_returns_false(self, authz):
        """Revoking twice returns False the second time."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        first = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        second = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))

        assert first is True
        assert second is False


class TestBatchChecks:
    """Batch permission checks (check_any, check_all)."""

    def test_check_any_true_if_one_matches(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check_any("alice", ["write", "read"], ("doc", "1"))

    def test_check_any_false_if_none_match(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert not authz.check_any("alice", ["write", "admin"], ("doc", "1"))

    def test_check_all_true_if_all_match(self, authz):
        authz.set_hierarchy("doc", "admin", "write", "read")
        authz.grant("admin", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check_all("alice", ["admin", "write", "read"], ("doc", "1"))

    def test_check_all_false_if_any_missing(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert not authz.check_all("alice", ["read", "write"], ("doc", "1"))

    def test_check_all_empty_list_returns_true(self, authz):
        # Vacuous truth: user has all zero required permissions
        assert authz.check_all("alice", [], ("doc", "1"))

    def test_check_any_empty_list_returns_false(self, authz):
        # No permissions to check means none match
        assert not authz.check_any("alice", [], ("doc", "1"))


class TestAudit:
    """Audit and listing operations."""

    def test_explain_explains_direct_grant(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        explanations = authz.explain("alice", "read", ("doc", "1"))

        assert len(explanations) == 1
        assert "DIRECT" in explanations[0]

    def test_explain_explains_group_membership(self, authz):
        authz.grant("write", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))

        explanations = authz.explain("alice", "write", ("doc", "1"))

        assert len(explanations) >= 1
        assert any("GROUP" in exp for exp in explanations)

    def test_explain_explains_hierarchy(self, authz):
        authz.set_hierarchy("doc", "admin", "read")
        authz.grant("admin", resource=("doc", "1"), subject=("user", "alice"))

        explanations = authz.explain("alice", "read", ("doc", "1"))

        assert any("HIERARCHY" in exp for exp in explanations)

    def test_explain_returns_no_access_message(self, authz):
        explanations = authz.explain("alice", "read", ("doc", "1"))

        assert len(explanations) == 1
        assert "NO ACCESS" in explanations[0]

    def test_list_users_lists_users(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "1"), subject=("user", "bob"))

        users = authz.list_users("read", ("doc", "1"))

        assert "alice" in users
        assert "bob" in users

    def test_list_users_includes_group_members(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))

        users = authz.list_users("read", ("doc", "1"))

        assert "alice" in users

    def test_list_resources_lists_resources(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "2"), subject=("user", "alice"))

        docs = authz.list_resources("alice", "doc", "read")

        assert "1" in docs
        assert "2" in docs
