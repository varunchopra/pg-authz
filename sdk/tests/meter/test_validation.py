"""Namespace validation tests for meter module."""

import pytest
from postkit.meter import MeterError


class TestNamespaceValidation:
    """Tests for meter._validate_namespace()"""

    def test_valid_namespaces(self, make_meter):
        """Valid namespace formats should be accepted."""
        valid = ["default", "tenant_123", "org:my-org", "MyOrg", "a" * 1024]
        for ns in valid:
            client = make_meter(ns)
            client.allocate("user-1", "api.calls", 100, "credits")

    def test_rejects_null(self, make_meter):
        with pytest.raises(MeterError):
            make_meter(None)

    def test_rejects_empty(self, make_meter):
        with pytest.raises(MeterError):
            make_meter("")

    def test_rejects_whitespace_only(self, make_meter):
        with pytest.raises(MeterError):
            make_meter("   ")

    def test_rejects_leading_whitespace(self, make_meter):
        with pytest.raises(MeterError):
            make_meter(" leading")

    def test_rejects_trailing_whitespace(self, make_meter):
        with pytest.raises(MeterError):
            make_meter("trailing ")

    def test_rejects_control_characters(self, make_meter):
        with pytest.raises(MeterError):
            make_meter("has\ttab")

    def test_rejects_over_max_length(self, make_meter):
        with pytest.raises(MeterError):
            make_meter("a" * 1025)
