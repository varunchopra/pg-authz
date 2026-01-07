"""Tests for audit logging and actor context."""

import pytest


class TestSetActor:
    """Tests for config.set_actor()"""

    def test_captures_actor_in_audit(self, config, test_helpers):
        """Actor context is captured in audit events."""
        config.set_actor("user:alice")
        config.set("prompts/bot", {"v": 1})

        events = config.get_audit_events(event_type="entry_created")

        assert len(events) >= 1
        assert events[0]["actor_id"] == "user:alice"

    def test_captures_request_id(self, config, test_helpers):
        """Request ID is captured in audit events."""
        config.set_actor("user:alice", request_id="req-123")
        config.set("prompts/bot", {"v": 1})

        events = config.get_audit_events(event_type="entry_created")

        assert events[0]["request_id"] == "req-123"

    def test_captures_on_behalf_of(self, config, test_helpers):
        """on_behalf_of is captured in audit events."""
        config.set_actor(
            "user:admin-bob",
            on_behalf_of="user:customer-alice",
            reason="support_ticket:12345",
        )
        config.set("prompts/bot", {"v": 1})

        events = config.get_audit_events(event_type="entry_created")

        assert events[0]["actor_id"] == "user:admin-bob"
        assert events[0]["on_behalf_of"] == "user:customer-alice"
        assert events[0]["reason"] == "support_ticket:12345"

    def test_reason_without_on_behalf_of(self, config, test_helpers):
        """Reason can be set without on_behalf_of."""
        config.set_actor("service:deploy", reason="deployment:v1.2.3")
        config.set("prompts/bot", {"v": 1})

        events = config.get_audit_events(event_type="entry_created")

        assert events[0]["actor_id"] == "service:deploy"
        assert events[0]["reason"] == "deployment:v1.2.3"
        assert events[0]["on_behalf_of"] is None


class TestClearActor:
    """Tests for config.clear_actor()"""

    def test_clears_actor_context(self, config, test_helpers):
        """clear_actor() removes actor context."""
        config.set_actor("user:alice", request_id="req-123")
        config.set("prompts/bot1", {"v": 1})

        config.clear_actor()
        config.set("prompts/bot2", {"v": 1})

        events = config.get_audit_events(key="prompts/bot2")

        assert events[0]["actor_id"] is None
        assert events[0]["request_id"] is None


class TestAuditEvents:
    """Tests for audit event logging."""

    def test_entry_created_event(self, config, test_helpers):
        """entry_created event is logged on set()."""
        config.set("prompts/bot", {"template": "hello"})

        events = config.get_audit_events(event_type="entry_created")

        assert len(events) >= 1
        assert events[0]["key"] == "prompts/bot"
        assert events[0]["version"] == 1
        assert events[0]["new_value"]["template"] == "hello"

    def test_entry_created_captures_old_value(self, config, test_helpers):
        """entry_created captures old value when updating."""
        config.set("prompts/bot", {"template": "v1"})
        config.set("prompts/bot", {"template": "v2"})

        events = config.get_audit_events(key="prompts/bot", event_type="entry_created")

        # Most recent first
        assert events[0]["version"] == 2
        assert events[0]["old_value"]["template"] == "v1"
        assert events[0]["new_value"]["template"] == "v2"

    def test_entry_activated_event(self, config, test_helpers):
        """entry_activated event is logged on activate()."""
        config.set("prompts/bot", {"template": "v1"})
        config.set("prompts/bot", {"template": "v2"})
        config.activate("prompts/bot", 1)

        events = config.get_audit_events(event_type="entry_activated")

        assert len(events) >= 1
        assert events[0]["key"] == "prompts/bot"
        assert events[0]["version"] == 1

    def test_entry_deleted_event(self, config, test_helpers):
        """entry_deleted event is logged on delete()."""
        config.set("prompts/bot", {"template": "hello"})
        config.delete("prompts/bot")

        events = config.get_audit_events(event_type="entry_deleted")

        assert len(events) >= 1
        assert events[0]["key"] == "prompts/bot"
        assert events[0]["old_value"]["template"] == "hello"

    def test_entry_version_deleted_event(self, config, test_helpers):
        """entry_version_deleted event is logged on delete_version()."""
        config.set("prompts/bot", {"template": "v1"})
        config.set("prompts/bot", {"template": "v2"})
        config.delete_version("prompts/bot", 1)

        events = config.get_audit_events(event_type="entry_version_deleted")

        assert len(events) >= 1
        assert events[0]["key"] == "prompts/bot"
        assert events[0]["version"] == 1

    def test_audit_without_actor(self, config, test_helpers):
        """Audit events are created even without actor context."""
        config.set("prompts/bot", {"template": "hello"})

        events = config.get_audit_events()

        assert len(events) >= 1
        assert events[0]["actor_id"] is None


class TestAuditPartitions:
    """Tests for audit partition management."""

    def test_create_partition(self, config, test_helpers):
        """create_audit_partition() creates a partition."""
        test_helpers.cursor.execute(
            "SELECT config.create_audit_partition(%s, %s)",
            (2099, 6),
        )
        result = test_helpers.cursor.fetchone()[0]

        assert result == "audit_events_y2099m06"

        # Cleanup
        test_helpers.cursor.execute("DROP TABLE IF EXISTS config.audit_events_y2099m06")

    def test_create_partition_returns_null_if_exists(self, config, test_helpers):
        """create_audit_partition() returns NULL if partition exists."""
        # Create first
        test_helpers.cursor.execute(
            "SELECT config.create_audit_partition(%s, %s)",
            (2098, 7),
        )

        # Try again
        test_helpers.cursor.execute(
            "SELECT config.create_audit_partition(%s, %s)",
            (2098, 7),
        )
        result = test_helpers.cursor.fetchone()[0]

        assert result is None

        # Cleanup
        test_helpers.cursor.execute("DROP TABLE IF EXISTS config.audit_events_y2098m07")

    def test_validates_month_bounds(self, config, test_helpers):
        """create_audit_partition() validates month range."""
        with pytest.raises(Exception) as exc_info:
            test_helpers.cursor.execute(
                "SELECT config.create_audit_partition(%s, %s)",
                (2024, 13),
            )
        assert "Month must be between 1 and 12" in str(exc_info.value)

    def test_drop_old_partitions(self, config, test_helpers):
        """drop_audit_partitions() drops old partitions."""
        # Create partitions for testing (far in past)
        test_helpers.cursor.execute(
            "SELECT config.create_audit_partition(%s, %s)",
            (2010, 1),
        )
        test_helpers.cursor.execute(
            "SELECT config.create_audit_partition(%s, %s)",
            (2010, 2),
        )

        # Drop partitions older than 1 month (should drop both 2010 partitions)
        test_helpers.cursor.execute("SELECT config.drop_audit_partitions(%s)", (1,))
        dropped = [row[0] for row in test_helpers.cursor.fetchall()]

        assert "audit_events_y2010m01" in dropped
        assert "audit_events_y2010m02" in dropped

    def test_drop_partitions_keeps_recent(self, config, test_helpers):
        """drop_audit_partitions() keeps recent partitions."""
        # Create a future partition (should never be dropped)
        test_helpers.cursor.execute(
            "SELECT config.create_audit_partition(%s, %s)",
            (2099, 12),
        )

        # Drop with keep_months=1 - future partition should remain
        test_helpers.cursor.execute("SELECT config.drop_audit_partitions(%s)", (1,))
        dropped = [row[0] for row in test_helpers.cursor.fetchall()]

        assert "audit_events_y2099m12" not in dropped

        # Cleanup
        test_helpers.cursor.execute("DROP TABLE IF EXISTS config.audit_events_y2099m12")


class TestGetStats:
    """Tests for config.get_stats()"""

    def test_returns_key_counts(self, config):
        """get_stats() returns key and version counts."""
        config.set("prompts/a", {"v": 1})
        config.set("prompts/a", {"v": 2})
        config.set("prompts/b", {"v": 1})
        config.set("flags/x", {"enabled": True})

        stats = config.get_stats()

        assert stats["total_keys"] == 3
        assert stats["total_versions"] == 4

    def test_returns_keys_by_prefix(self, config):
        """get_stats() returns breakdown by prefix."""
        config.set("prompts/a", {"v": 1})
        config.set("prompts/b", {"v": 1})
        config.set("flags/x", {"enabled": True})

        stats = config.get_stats()

        assert stats["keys_by_prefix"]["prompts"] == 2
        assert stats["keys_by_prefix"]["flags"] == 1


class TestCleanupOldVersions:
    """Tests for config.cleanup_old_versions()"""

    def test_removes_old_inactive_versions(self, config, test_helpers):
        """cleanup_old_versions() removes old inactive versions."""
        # Create many versions
        for i in range(5):
            config.set("prompts/bot", {"v": i + 1})

        # Keep only 2 inactive versions (plus active = 3 total)
        deleted = config.cleanup_old_versions(keep_versions=2)

        assert deleted == 2  # Deleted v1 and v2
        assert test_helpers.count_versions("prompts/bot") == 3

    def test_cleanup_when_active_not_newest(self, config, test_helpers):
        """cleanup works correctly when active version isn't the newest."""
        # Create v1, v2, v3
        config.set("prompts/bot", {"v": 1})
        config.set("prompts/bot", {"v": 2})
        config.set("prompts/bot", {"v": 3})

        # Activate v1 (oldest) - now v2 and v3 are inactive
        config.activate("prompts/bot", 1)

        # Keep 1 inactive version - should delete v2 (older inactive)
        deleted = config.cleanup_old_versions(keep_versions=1)

        assert deleted == 1
        # Should have: v1 (active), v3 (kept inactive)
        assert test_helpers.count_versions("prompts/bot") == 2


class TestAuditSecurityValidation:
    """Tests for audit event query security."""

    def test_rejects_invalid_column_names(self, config):
        """SQL injection via column name is prevented."""
        # Attempt to inject SQL via column name
        with pytest.raises(ValueError, match="Invalid column name"):
            config._get_audit_events(filters={"1=1; DROP TABLE--": "value"})

    def test_rejects_column_names_with_spaces(self, config):
        """Column names with spaces are rejected."""
        with pytest.raises(ValueError, match="Invalid column name"):
            config._get_audit_events(filters={"key or 1=1": "value"})

    def test_rejects_column_names_with_operators(self, config):
        """Column names with SQL operators are rejected."""
        with pytest.raises(ValueError, match="Invalid column name"):
            config._get_audit_events(filters={"key=": "value"})

    def test_accepts_valid_column_names(self, config):
        """Valid Python identifiers are accepted as column names."""
        # This should not raise - 'key' is a valid identifier
        result = config._get_audit_events(filters={"key": "nonexistent"})
        assert result == []  # No matching events, but query executed safely
