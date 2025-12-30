"""Tests for docstring parser."""

from gendocs.extractors import _parse_docstring


def test_brief():
    doc = """Short description."""
    result = _parse_docstring(doc)
    assert result.brief == "Short description."


def test_multiline_brief():
    doc = """
    First line of description
    continues here.

    Args:
        x: A parameter
    """
    result = _parse_docstring(doc)
    assert result.brief == "First line of description continues here."


def test_params():
    doc = """
    Do something.

    Args:
        name: The name
        value: The value to set
    """
    result = _parse_docstring(doc)
    assert result.params == {"name": "The name", "value": "The value to set"}


def test_returns_simple():
    doc = """
    Do something.

    Returns:
        The result value
    """
    result = _parse_docstring(doc)
    assert result.returns == "The result value"


def test_returns_multiline():
    doc = """
    Get statistics.

    Returns:
        Dictionary with:
        - count: Number of items
        - total: Total value

    Example:
        stats = get_stats()
    """
    result = _parse_docstring(doc)
    assert "Dictionary with:" in result.returns
    assert "- count: Number of items" in result.returns
    assert "- total: Total value" in result.returns


def test_example():
    doc = """
    Do something.

    Example:
        result = do_something()
        print(result)
    """
    result = _parse_docstring(doc)
    assert len(result.examples) == 1
    assert "result = do_something()" in result.examples[0]
    assert "print(result)" in result.examples[0]


def test_example_multiline_code():
    doc = """
    Grant permission.

    Example:
        authz.grant("admin", resource=("repo", "api"),
                   subject=("team", "eng"))
    """
    result = _parse_docstring(doc)
    assert len(result.examples) == 1
    assert 'authz.grant("admin"' in result.examples[0]


def test_full_docstring():
    doc = """
    Grant a permission on a resource.

    Args:
        permission: The permission to grant
        resource: The resource tuple

    Returns:
        The tuple ID

    Example:
        authz.grant("read", resource=("doc", "1"))
    """
    result = _parse_docstring(doc)
    assert result.brief == "Grant a permission on a resource."
    assert result.params == {
        "permission": "The permission to grant",
        "resource": "The resource tuple",
    }
    assert result.returns == "The tuple ID"
    assert len(result.examples) == 1


def test_empty_docstring():
    result = _parse_docstring(None)
    assert result.brief == ""
    assert result.params == {}
    assert result.returns is None
    assert result.examples == []

    result = _parse_docstring("")
    assert result.brief == ""
