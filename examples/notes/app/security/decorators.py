"""
Authentication decorator with automatic validation.

Usage:
    from app.security import authenticated, RequestContext

    @authenticated              # User auth only
    def user_route(ctx: RequestContext):
        ...

    @authenticated(org=True)    # Requires org context
    def org_route(ctx: RequestContext, org_id: str):
        ...

    @authenticated(org=True, admin=True)  # Requires org admin
    def admin_route(ctx: RequestContext, org_id: str):
        ...
"""

import uuid
from functools import wraps
from typing import Callable, Optional, TypeVar, Union

from flask import g, jsonify, redirect, request, session, url_for
from werkzeug.exceptions import BadRequest

from .authenticators import authenticate_request
from .context import RequestContext, set_context
from .permissions import _check_org_admin, _check_org_membership
from .validators import validate_url_params

F = TypeVar("F", bound=Callable)


def _is_api_request() -> bool:
    """Check if request expects JSON response."""
    return (
        request.accept_mimetypes.best == "application/json"
        or request.is_json
        or request.path.startswith("/api/")
    )


def _error_response(code: int, message: str, redirect_url: Optional[str] = None):
    """Return appropriate error response based on request type."""
    if _is_api_request():
        return jsonify({"error": message}), code
    if redirect_url:
        return redirect(redirect_url)
    return message, code


def _resolve_org_id(kwargs: dict) -> Optional[str]:
    """
    Resolve org_id from multiple sources. Errors on conflict.

    Priority: URL param > Header > Session
    """
    sources = [
        kwargs.get("org_id"),
        request.headers.get("X-Org-Id"),
        session.get("current_org_id"),
    ]
    unique = {s for s in sources if s}

    if len(unique) > 1:
        raise BadRequest("Conflicting org_id values in request")

    return next(iter(unique), None)


def _set_audit_actor(ctx: RequestContext) -> None:
    """Set actor context in authn/authz for audit trails."""
    from ..db import get_authn, get_authz

    authn = get_authn()
    authn.set_actor(
        actor_id=ctx.actor_id,
        on_behalf_of=ctx.on_behalf_of,
        reason=ctx.impersonation.reason if ctx.impersonation else None,
    )

    if ctx.org_id:
        authz = get_authz(ctx.org_id)
        authz.set_actor(
            actor_id=ctx.actor_id,
            on_behalf_of=ctx.on_behalf_of,
            reason=ctx.impersonation.reason if ctx.impersonation else None,
        )


def authenticated(
    f: Optional[F] = None,
    *,
    org: bool = False,
    admin: bool = False,
    validate_params: bool = True,
) -> Union[F, Callable[[F], F]]:
    """
    Authentication decorator with automatic validation.

    Args:
        org: Require organization context
        admin: Require org admin permission (implies org=True)
        validate_params: Auto-validate URL params against org (default True)

    The decorated function receives RequestContext as first argument.

    URL parameters (user_id, team_id, note_id) are automatically validated
    to belong to the current org. Disable with validate_params=False.
    """
    require_org = org or admin

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            from ..db import get_authn

            # Step 1: Authenticate
            auth_result = authenticate_request(get_authn())

            if not auth_result:
                return _error_response(
                    401,
                    "unauthorized",
                    url_for("views.auth.login") if not _is_api_request() else None,
                )

            # Step 2: Resolve org context
            org_id = None
            if require_org:
                try:
                    org_id = _resolve_org_id(kwargs)
                except BadRequest as e:
                    return _error_response(400, str(e))

                if not org_id:
                    return _error_response(
                        400,
                        "org_id required",
                        url_for("views.orgs.select") if not _is_api_request() else None,
                    )

                # Verify membership
                if not _check_org_membership(auth_result.user_id, org_id):
                    session.pop("current_org_id", None)
                    return _error_response(403, "not a member of this organization")

                # Check admin if required
                if admin and not _check_org_admin(auth_result.user_id, org_id):
                    return _error_response(403, "admin required")

            # Step 3: Validate URL parameters (automatic)
            if require_org and validate_params and org_id:
                try:
                    # Filter out org_id from validation (it's the reference)
                    params_to_validate = {
                        k: v for k, v in kwargs.items() if k != "org_id"
                    }
                    validate_url_params(org_id, params_to_validate)
                except Exception:
                    return _error_response(404, "not found")

            # Step 4: Create immutable context
            ctx = RequestContext(
                user_id=auth_result.user_id,
                auth_method=auth_result.auth_method,
                org_id=org_id,
                impersonation=auth_result.impersonation,
                request_id=g.get("request_id", str(uuid.uuid4())),
                ip_address=request.remote_addr or "",
                user_agent=request.headers.get("User-Agent", "")[:1024],
            )
            set_context(ctx)

            # Step 5: Set audit actor
            _set_audit_actor(ctx)

            # Step 6: Set template context for impersonation banner
            g.is_impersonating = ctx.is_impersonating
            if ctx.impersonation:
                g.impersonator_id = ctx.impersonation.impersonator_id
                g.impersonator_email = ctx.impersonation.impersonator_email
                g.impersonation_reason = ctx.impersonation.reason

            # Step 7: Set g.org_id for backward compatibility
            if org_id:
                g.org_id = org_id

            return func(ctx, *args, **kwargs)

        return wrapper

    if f is not None:
        return decorator(f)
    return decorator
