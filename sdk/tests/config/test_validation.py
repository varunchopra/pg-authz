"""Namespace validation tests for config module."""

import pytest
from postkit.config.client import ConfigError


class TestNamespaceValidation:
    """Namespace must be 1-1024 chars, no control chars or leading/trailing whitespace."""

    def test_valid_namespaces(self, make_config):
        """Valid namespace formats should be accepted."""
        valid = ["default", "tenant_123", "org:my-org", "MyOrg", "a" * 1024]
        for ns in valid:
            client = make_config(ns)
            client.set("test.key", "value")
            assert client.get("test.key") is not None

    def test_rejects_null(self, make_config):
        with pytest.raises(ConfigError):
            make_config(None)

    def test_rejects_empty(self, make_config):
        with pytest.raises(ConfigError):
            make_config("")

    def test_rejects_whitespace_only(self, make_config):
        with pytest.raises(ConfigError):
            make_config("   ")

    def test_rejects_leading_whitespace(self, make_config):
        with pytest.raises(ConfigError):
            make_config(" leading")

    def test_rejects_trailing_whitespace(self, make_config):
        with pytest.raises(ConfigError):
            make_config("trailing ")

    def test_rejects_control_characters(self, make_config):
        with pytest.raises(ConfigError):
            make_config("has\ttab")

    def test_rejects_over_max_length(self, make_config):
        with pytest.raises(ConfigError):
            make_config("a" * 1025)
