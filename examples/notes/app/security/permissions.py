"""
Permission checking utilities.

Usage:
    from app.security import check_permission, is_org_admin

    @authenticated(org=True)
    def my_route(ctx: RequestContext, note_id: str):
        if not check_permission(ctx, "edit", ("note", note_id)):
            return "forbidden", 403
"""

from typing import Tuple

from .context import RequestContext


def check_permission(
    ctx: RequestContext,
    permission: str,
    resource: Tuple[str, str],
) -> bool:
    """
    Check if current context has permission on resource.

    For API keys: checks BOTH user permission AND key scope.
    For sessions: checks only user permission.

    Args:
        ctx: Request context
        permission: Permission name (e.g., "view", "edit", "delete")
        resource: (resource_type, resource_id) tuple

    Returns:
        True if permission granted, False otherwise
    """
    if not ctx.org_id:
        return False

    from ..db import get_authz

    authz = get_authz(ctx.org_id)

    # User must have permission
    if not authz.check(("user", ctx.user_id), permission, resource):
        return False

    # If API key auth, key must also have scope
    if ctx.api_key_id:
        resource_type, resource_id = resource

        # Check specific resource
        has_specific = authz.check(("api_key", ctx.api_key_id), permission, resource)

        # Check wildcard (e.g., note:*)
        has_wildcard = authz.check(
            ("api_key", ctx.api_key_id), permission, (resource_type, "*")
        )

        if not (has_specific or has_wildcard):
            return False

    return True


def is_org_member(ctx: RequestContext) -> bool:
    """Check if current user is member of current org."""
    if not ctx.org_id:
        return False

    from ..db import get_db

    with get_db().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM org_memberships WHERE user_id = %s AND org_id = %s",
            (ctx.user_id, ctx.org_id),
        )
        return cur.fetchone() is not None


def is_org_admin(ctx: RequestContext) -> bool:
    """Check if current user is org admin."""
    if not ctx.org_id:
        return False

    from ..db import get_authz

    return get_authz(ctx.org_id).check(
        ("user", ctx.user_id), "admin", ("org", ctx.org_id)
    )


def is_org_owner(ctx: RequestContext) -> bool:
    """Check if current user is org owner."""
    if not ctx.org_id:
        return False

    from ..db import get_authz

    return get_authz(ctx.org_id).check(
        ("user", ctx.user_id), "owner", ("org", ctx.org_id)
    )


def _check_org_membership(user_id: str, org_id: str) -> bool:
    """Internal: Check if user is member of org (for decorator)."""
    from ..db import get_db

    with get_db().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM org_memberships WHERE user_id = %s AND org_id = %s",
            (user_id, org_id),
        )
        return cur.fetchone() is not None


def _check_org_admin(user_id: str, org_id: str) -> bool:
    """Internal: Check if user is admin of org (for decorator)."""
    from ..db import get_authz

    return get_authz(org_id).check(("user", user_id), "admin", ("org", org_id))
