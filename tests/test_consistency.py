"""
Consistency and statistics tests for pg-authz.

Tests for:
- verify_computed: checking computed table consistency
- repair_computed: fixing consistency issues
- stats: namespace statistics for monitoring
- Deduplication: ensuring unique computed entries
"""

import pytest


class TestStatistics:
    """Test the stats monitoring function."""

    def test_empty_namespace_returns_zeros(self, authz):
        """Empty namespace returns all zeros."""
        stats = authz.stats()
        assert stats["tuple_count"] == 0
        assert stats["computed_count"] == 0
        assert stats["hierarchy_rule_count"] == 0
        assert stats["amplification_factor"] is None  # 0/0
        assert stats["unique_users"] == 0
        assert stats["unique_resources"] == 0

    def test_stats_reflect_tuples_and_computed(self, authz):
        """Stats accurately reflect tuple and computed counts."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "2"), subject=("user", "bob"))

        stats = authz.stats()
        assert stats["tuple_count"] == 2
        assert stats["computed_count"] == 2
        assert stats["unique_users"] == 2
        assert stats["unique_resources"] == 2

    def test_stats_with_hierarchy_shows_amplification(self, authz):
        """Stats show amplification when hierarchy expands permissions."""
        authz.set_hierarchy("doc", "admin", "write", "read")
        authz.grant("admin", resource=("doc", "1"), subject=("user", "alice"))

        stats = authz.stats()
        assert stats["tuple_count"] == 1
        assert stats["computed_count"] == 3  # admin, write, read
        assert stats["hierarchy_rule_count"] == 2  # admin->write, write->read
        assert stats["amplification_factor"] == 3.0

    def test_stats_with_groups_shows_amplification(self, authz):
        """Stats show amplification from group expansion."""
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "bob"))
        authz.grant("read", resource=("doc", "1"), subject=("team", "eng"))

        stats = authz.stats()
        assert stats["tuple_count"] == 3
        # Computed includes: team:eng (alice:member, bob:member) + doc:1 (alice:read, bob:read)
        assert stats["computed_count"] == 4
        assert stats["unique_users"] == 2
        assert stats["unique_resources"] == 2  # team:eng and doc:1


class TestVerifyComputed:
    """Consistency checking functionality."""

    def test_verify_clean_state_returns_empty(self, authz):
        """verify() returns nothing when computed is correct."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.verify() == []

    def test_verify_detects_missing_computed(self, authz, test_helpers):
        """verify() detects when computed table is missing entries."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        test_helpers.delete_computed(("doc", "1"))

        issues = authz.verify()
        assert any(i["status"] == "missing" for i in issues)

    def test_verify_detects_extra_computed(self, authz, test_helpers):
        """verify() detects spurious entries in computed table."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        test_helpers.insert_computed("admin", ("doc", "1"), "alice")

        issues = authz.verify()
        assert any(i["status"] == "extra" for i in issues)

    def test_verify_with_hierarchy(self, authz):
        """verify() correctly checks hierarchy-expanded permissions."""
        authz.set_hierarchy("doc", "admin", "write", "read")
        authz.grant("admin", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.verify() == []

    def test_verify_with_groups(self, authz):
        """verify() correctly checks group-expanded permissions."""
        authz.grant("read", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "bob"))

        assert authz.verify() == []

    def test_verify_with_hierarchy_and_groups(self, authz):
        """verify() handles combined hierarchy + group expansion."""
        authz.set_hierarchy("doc", "admin", "read")
        authz.grant("admin", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))

        assert authz.verify() == []

    def test_verify_detects_orphaned_computed(self, authz, test_helpers):
        """verify() detects computed entries with no backing tuples."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        test_helpers.delete_tuples(("doc", "1"))

        issues = authz.verify()
        assert any(i["status"] == "orphaned" for i in issues)


class TestRepairComputed:
    """repair() functionality."""

    def test_repair_fixes_missing(self, authz, test_helpers):
        """repair() restores missing computed entries."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        test_helpers.delete_computed(("doc", "1"))

        assert not authz.check("alice", "read", ("doc", "1"))

        authz.repair()

        assert authz.check("alice", "read", ("doc", "1"))

    def test_repair_fixes_extra(self, authz, test_helpers):
        """repair() removes spurious computed entries."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        test_helpers.insert_computed("admin", ("doc", "1"), "alice")

        authz.repair()

        assert authz.check("alice", "read", ("doc", "1"))
        assert not authz.check("alice", "admin", ("doc", "1"))


class TestDeduplication:
    """Ensure computed entries are properly deduplicated."""

    def test_user_in_many_groups_single_entry(self, authz, test_helpers):
        """User in multiple groups with same permission gets one computed entry."""
        for team in ["team-a", "team-b", "team-c"]:
            authz.grant("read", resource=("doc", "1"), subject=("team", team))
            authz.grant("member", resource=("team", team), subject=("user", "alice"))

        assert authz.check("alice", "read", ("doc", "1"))
        assert (
            test_helpers.count_computed(
                resource=("doc", "1"), permission="read", user_id="alice"
            )
            == 1
        )

    def test_direct_and_group_single_entry(self, authz, test_helpers):
        """User with direct grant and group membership gets one computed entry."""
        authz.grant("read", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert (
            test_helpers.count_computed(
                resource=("doc", "1"), permission="read", user_id="alice"
            )
            == 1
        )

    def test_diamond_hierarchy_single_entry(self, authz, test_helpers):
        """Diamond hierarchy pattern produces one entry per implied permission."""
        # admin -> write -> view
        # admin -> read -> view
        authz.set_hierarchy("doc", "admin", "write")
        authz.add_hierarchy_rule("doc", "admin", "read")
        authz.add_hierarchy_rule("doc", "write", "view")
        authz.add_hierarchy_rule("doc", "read", "view")

        authz.grant("admin", resource=("doc", "1"), subject=("user", "alice"))

        # view is implied by both write and read, should still be one entry
        assert (
            test_helpers.count_computed(
                resource=("doc", "1"), permission="view", user_id="alice"
            )
            == 1
        )
