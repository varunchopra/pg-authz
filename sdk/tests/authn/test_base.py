"""Tests for base client functionality (S13, S14, S16)."""

import pytest
from postkit.authn import AuthnClient
from postkit.base import (
    CheckViolationError,
    ForeignKeyViolationError,
    PostkitError,
    UniqueViolationError,
)
from psycopg.rows import dict_row, kwargs_row


class TestRowFactoryValidation:
    """Tests for S13: Row factory detection."""

    def test_rejects_dict_row_factory(self, db_connection):
        """Cursor with dict_row should be rejected at init."""
        cursor = db_connection.cursor(row_factory=dict_row)
        try:
            with pytest.raises(ValueError, match="tuple row factory"):
                AuthnClient(cursor, "test_reject_dict")
        finally:
            cursor.close()

    def test_rejects_kwargs_row_factory(self, db_connection):
        """Cursor with kwargs_row should be rejected at init."""
        cursor = db_connection.cursor(row_factory=kwargs_row)
        try:
            with pytest.raises(ValueError, match="tuple row factory"):
                AuthnClient(cursor, "test_reject_kwargs")
        finally:
            cursor.close()

    def test_accepts_default_row_factory(self, db_connection):
        """Default tuple row factory should be accepted."""
        cursor = db_connection.cursor()
        try:
            client = AuthnClient(cursor, "test_accept_default")
            assert client is not None
            assert client.namespace == "test_accept_default"
        finally:
            cursor.close()

    def test_error_message_is_helpful(self, db_connection):
        """Error message should explain what to do."""
        cursor = db_connection.cursor(row_factory=dict_row)
        try:
            with pytest.raises(ValueError) as exc_info:
                AuthnClient(cursor, "test_error_msg")

            msg = str(exc_info.value)
            assert "dict_row" in msg or "kwargs_row" in msg
            assert "SDK returns dicts automatically" in msg
        finally:
            cursor.close()


class TestErrorHandling:
    """Tests for S14: SQLSTATE preservation."""

    def test_unique_violation_raises_specific_exception(self, authn):
        """Duplicate email should raise UniqueViolationError."""
        authn.create_user("duplicate@example.com", "hash1")

        with pytest.raises(UniqueViolationError) as exc_info:
            authn.create_user("duplicate@example.com", "hash2")

        assert exc_info.value.sqlstate == "23505"

    def test_unique_violation_inherits_from_postkit_error(self, authn):
        """UniqueViolationError should be catchable as PostkitError."""
        authn.create_user("inherit_test@example.com", "hash1")

        with pytest.raises(PostkitError) as exc_info:
            authn.create_user("inherit_test@example.com", "hash2")

        # Should be the more specific type
        assert isinstance(exc_info.value, UniqueViolationError)
        assert exc_info.value.sqlstate == "23505"

    def test_error_message_preserved(self, authn):
        """Original error message should be preserved."""
        authn.create_user("msg_test@example.com", "hash1")

        with pytest.raises(UniqueViolationError) as exc_info:
            authn.create_user("msg_test@example.com", "hash2")

        # Message should contain useful info
        msg = str(exc_info.value)
        assert (
            "unique" in msg.lower()
            or "duplicate" in msg.lower()
            or "already exists" in msg.lower()
        )

    def test_foreign_key_violation_class_exists(self):
        """ForeignKeyViolationError should be importable."""
        assert issubclass(ForeignKeyViolationError, PostkitError)

    def test_check_violation_class_exists(self):
        """CheckViolationError should be importable."""
        assert issubclass(CheckViolationError, PostkitError)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_all_exceptions_have_sqlstate_attribute(self):
        """All exception classes should support sqlstate."""
        for exc_class in [
            PostkitError,
            UniqueViolationError,
            ForeignKeyViolationError,
            CheckViolationError,
        ]:
            exc = exc_class("test message", sqlstate="12345")
            assert exc.sqlstate == "12345"
            assert str(exc) == "test message"

    def test_sqlstate_defaults_to_none(self):
        """sqlstate should default to None when not provided."""
        exc = PostkitError("test message")
        assert exc.sqlstate is None

    def test_exception_inheritance(self):
        """All specific exceptions should inherit from PostkitError."""
        assert issubclass(UniqueViolationError, PostkitError)
        assert issubclass(ForeignKeyViolationError, PostkitError)
        assert issubclass(CheckViolationError, PostkitError)

        # And from Exception
        assert issubclass(PostkitError, Exception)


class TestNormalizeValue:
    """Tests for value type normalization in _normalize_value."""

    def test_uuid_normalized_to_str(self, authn):
        """UUID values from DB are converted to str."""
        user_id = authn.create_user("uuid_test@example.com", "hash")
        user = authn.get_user(user_id)

        # Verify returned user_id in dict is a string, not UUID object
        assert isinstance(user["user_id"], str), (
            f"Expected str, got {type(user['user_id'])}"
        )
        assert len(user["user_id"]) == 36  # UUID string format: 8-4-4-4-12

    def test_ipv4_address_normalized_to_str(self, authn):
        """IPv4Address values from DB are converted to str."""
        user_id = authn.create_user("ipv4_test@example.com", "hash")
        authn.create_session(user_id, "token_hash", ip_address="192.168.1.100")
        sessions = authn.list_sessions(user_id)

        ip = sessions[0]["ip_address"]
        assert isinstance(ip, str), f"Expected str, got {type(ip)}"
        assert ip == "192.168.1.100"

    def test_ipv6_address_normalized_to_str(self, authn):
        """IPv6Address values from DB are converted to str."""
        user_id = authn.create_user("ipv6_test@example.com", "hash")
        authn.create_session(user_id, "token_hash", ip_address="::1")
        sessions = authn.list_sessions(user_id)

        ip = sessions[0]["ip_address"]
        assert isinstance(ip, str), f"Expected str, got {type(ip)}"
