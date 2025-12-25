"""
Input validation tests for pg-authz.

Tests for:
- Boundary conditions (max length, min length)
- Invalid input handling
- Special characters
- Edge cases
- SDK validation behavior
- Exception handling
"""

import pytest
import psycopg
from sdk import AuthzValidationError, AuthzCycleError


class TestBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def test_max_length_identifiers(self, authz):
        """Identifiers at max length (1024) work correctly."""
        long_id = "a" * 1024
        authz.grant("read", resource=("doc", long_id), subject=("user", "alice"))
        assert authz.check("alice", "read", ("doc", long_id))

    def test_identifier_over_max_length_rejected(self, authz):
        """Identifiers over 1024 chars are rejected."""
        too_long = "a" * 1025
        with pytest.raises(AuthzValidationError, match="exceeds maximum length"):
            authz.grant("read", resource=("doc", too_long), subject=("user", "alice"))

    def test_single_char_identifiers(self, authz):
        """Single character identifiers work."""
        authz.grant("r", resource=("d", "1"), subject=("user", "a"))
        assert authz.check("a", "r", ("d", "1"))

    def test_numeric_looking_ids(self, authz):
        """IDs that look like numbers work correctly."""
        authz.grant("read", resource=("doc", "12345"), subject=("user", "67890"))
        assert authz.check("67890", "read", ("doc", "12345"))

    def test_uuid_style_ids(self, authz):
        """UUID-style IDs work correctly."""
        uuid_id = "550e8400-e29b-41d4-a716-446655440000"
        authz.grant("read", resource=("doc", uuid_id), subject=("user", "alice"))
        assert authz.check("alice", "read", ("doc", uuid_id))

    def test_special_chars_in_ids(self, authz):
        """IDs with allowed special characters work."""
        # Underscores, hyphens, dots are typically allowed
        special_id = "my-doc_v1.0"
        authz.grant("read", resource=("doc", special_id), subject=("user", "alice"))
        assert authz.check("alice", "read", ("doc", special_id))

    def test_empty_id_rejected(self, authz):
        """Empty IDs are rejected."""
        with pytest.raises(AuthzValidationError):
            authz.grant("read", resource=("doc", ""), subject=("user", "alice"))

    def test_empty_user_rejected(self, authz):
        """Empty user IDs are rejected."""
        with pytest.raises(AuthzValidationError):
            authz.grant("read", resource=("doc", "1"), subject=("user", ""))

    def test_whitespace_only_rejected(self, authz):
        """Whitespace-only identifiers are rejected."""
        with pytest.raises(AuthzValidationError):
            authz.grant("read", resource=("doc", "   "), subject=("user", "alice"))

    def test_null_bytes_rejected_by_driver(self, authz):
        """Null bytes are rejected (by psycopg at protocol level, not our validation)."""
        with pytest.raises(psycopg.Error):
            authz.grant(
                "read", resource=("doc", "bad\x00id"), subject=("user", "alice")
            )


class TestBulkValidation:
    """Test bulk operation input validation."""

    def test_bulk_grant_rejects_empty_subject_id(self, authz):
        """bulk_grant rejects arrays with empty strings."""
        with pytest.raises(psycopg.Error, match="invalid values"):
            authz.bulk_grant(
                "read", resource=("doc", "1"), subject_ids=["alice", "", "bob"]
            )

    def test_bulk_grant_rejects_whitespace_only(self, authz):
        """bulk_grant rejects arrays with whitespace-only strings."""
        with pytest.raises(psycopg.Error, match="invalid values"):
            authz.bulk_grant(
                "read", resource=("doc", "1"), subject_ids=["alice", "   ", "bob"]
            )

    def test_bulk_grant_rejects_too_long(self, authz):
        """bulk_grant rejects arrays with overly long strings."""
        too_long = "a" * 1025
        with pytest.raises(psycopg.Error, match="invalid values"):
            authz.bulk_grant(
                "read", resource=("doc", "1"), subject_ids=["alice", too_long]
            )

    def test_bulk_grant_valid_array_succeeds(self, authz):
        """bulk_grant works with valid arrays."""
        count = authz.bulk_grant(
            "read", resource=("doc", "1"), subject_ids=["alice", "bob", "carol"]
        )
        assert count == 3
        assert authz.check("alice", "read", ("doc", "1"))
        assert authz.check("bob", "read", ("doc", "1"))
        assert authz.check("carol", "read", ("doc", "1"))


class TestSDKValidation:
    """Input validation - SDK raises exceptions for invalid inputs."""

    def test_invalid_resource_type_raises(self, authz):
        with pytest.raises(psycopg.Error, match="must start with lowercase"):
            authz.grant("read", resource=("INVALID", "1"), subject=("user", "alice"))

    def test_invalid_permission_raises(self, authz):
        with pytest.raises(psycopg.Error, match="must start with lowercase"):
            authz.grant("READ", resource=("doc", "1"), subject=("user", "alice"))

    def test_invalid_subject_type_raises(self, authz):
        with pytest.raises(psycopg.Error, match="must start with lowercase"):
            authz.grant("read", resource=("doc", "1"), subject=("USER", "alice"))

    def test_empty_resource_id_raises(self, authz):
        with pytest.raises(AuthzValidationError, match="cannot be empty"):
            authz.grant("read", resource=("doc", ""), subject=("user", "alice"))

    def test_flexible_resource_ids_allowed(self, authz):
        # IDs can have slashes, @, uppercase - they're flexible
        authz.grant(
            "read",
            resource=("doc", "acme/doc-1"),
            subject=("user", "alice@example.com"),
        )

        assert authz.check("alice@example.com", "read", ("doc", "acme/doc-1"))


class TestValidationEdgeCases:
    """Edge cases in input validation."""

    def test_unicode_in_ids(self, authz):
        """Unicode characters in IDs work correctly."""
        authz.grant("read", resource=("doc", "文档-1"), subject=("user", "用户-alice"))
        assert authz.check("用户-alice", "read", ("doc", "文档-1"))

    def test_special_chars_in_ids(self, authz):
        """Special characters in IDs work correctly."""
        authz.grant(
            "read",
            resource=("doc", "path/to/doc#section?v=1"),
            subject=("user", "alice+test@example.com"),
        )
        assert authz.check(
            "alice+test@example.com",
            "read",
            ("doc", "path/to/doc#section?v=1"),
        )


class TestExceptionHandling:
    """Test that SDK raises proper exception types."""

    def test_validation_error_on_empty_id(self, authz):
        """Empty ID raises AuthzValidationError."""
        with pytest.raises(AuthzValidationError):
            authz.grant("read", resource=("doc", ""), subject=("user", "alice"))

    def test_cycle_error_on_hierarchy_cycle(self, authz):
        """Hierarchy cycle raises AuthzCycleError."""
        authz.add_hierarchy_rule("doc", "admin", "write")
        authz.add_hierarchy_rule("doc", "write", "read")

        with pytest.raises(AuthzCycleError):
            authz.add_hierarchy_rule("doc", "read", "admin")
