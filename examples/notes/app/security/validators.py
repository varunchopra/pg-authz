"""
URL parameter validators.

Automatically validates that URL parameters (user_id, team_id, etc.)
belong to the current org context.

Usage:
    # Built-in validators run automatically in @authenticated(org=True)
    # To add custom validator:
    from app.security.validators import register_validator

    register_validator("project_id", lambda pid, org: is_project_in_org(pid, org))
"""

from typing import Callable, Dict

from flask import request
from werkzeug.exceptions import BadRequest, NotFound

# Registry: param_name -> validator(param_value, org_id) -> bool
_validators: Dict[str, Callable[[str, str], bool]] = {}


def register_validator(param_name: str, validator: Callable[[str, str], bool]) -> None:
    """
    Register a validator for a URL parameter.

    Args:
        param_name: Name of URL parameter (e.g., "user_id", "team_id")
        validator: Function(param_value, org_id) -> bool
    """
    _validators[param_name] = validator


def validate_url_params(org_id: str, kwargs: dict) -> None:
    """
    Validate URL parameters against org context.

    Raises NotFound if any registered param doesn't belong to org.
    Called automatically by @authenticated decorator.

    Args:
        org_id: Current organization ID
        kwargs: Route kwargs (URL parameters)
    """
    for param_name, param_value in kwargs.items():
        if param_name in _validators and param_value:
            if not _validators[param_name](param_value, org_id):
                raise NotFound(f"{param_name} not found")


def get_and_validate_param(kwargs: dict, param_name: str, org_id: str) -> str | None:
    """
    Get a parameter value and validate it belongs to org.

    Useful for parameters that might come from multiple sources.

    Args:
        kwargs: Route kwargs
        param_name: Parameter name
        org_id: Current org ID

    Returns:
        Parameter value if valid, None if not present

    Raises:
        NotFound if present but doesn't belong to org
    """
    sources = [
        kwargs.get(param_name),
        request.json.get(param_name) if request.is_json else None,
        request.form.get(param_name),
    ]

    unique = {s for s in sources if s}
    if len(unique) > 1:
        raise BadRequest(f"Conflicting {param_name} values in request")

    value = next(iter(unique), None)
    if value and param_name in _validators:
        if not _validators[param_name](value, org_id):
            raise NotFound(f"{param_name} not found")

    return value


# =============================================================================
# Built-in validators
# =============================================================================


def _is_org_member(user_id: str, org_id: str) -> bool:
    """Check if user is member of org."""
    from ..db import get_db

    with get_db().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM org_memberships WHERE user_id = %s AND org_id = %s",
            (user_id, org_id),
        )
        return cur.fetchone() is not None


def _is_team_in_org(team_id: str, org_id: str) -> bool:
    """Check if team belongs to org."""
    from ..db import get_db

    with get_db().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM teams WHERE team_id = %s AND org_id = %s",
            (team_id, org_id),
        )
        return cur.fetchone() is not None


def _is_note_in_org(note_id: str, org_id: str) -> bool:
    """Check if note belongs to org."""
    from ..db import get_db

    with get_db().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM notes WHERE note_id = %s AND org_id = %s",
            (note_id, org_id),
        )
        return cur.fetchone() is not None


# Register built-in validators
register_validator("user_id", _is_org_member)
register_validator("member_id", _is_org_member)  # Alias used in some routes
register_validator("team_id", _is_team_in_org)
register_validator("note_id", _is_note_in_org)
