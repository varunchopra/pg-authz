"""
Security module - authentication, authorization, and request context.

Usage:
    from app.security import authenticated, RequestContext, check_permission

    @authenticated(org=True)
    def my_route(ctx: RequestContext, org_id: str, user_id: str):
        # user_id is automatically validated to belong to org_id
        if not check_permission(ctx, "edit", ("note", note_id)):
            return "forbidden", 403
        ...
"""

# Context types
from .context import (
    AuthMethod,
    ImpersonationContext,
    OperatorAccessContext,
    OrgContext,
    RequestContext,
    UserContext,
    clear_context,
    get_context,
    set_context,
)

# Crypto utilities
from .crypto import (
    API_KEY_PREFIX,
    DUMMY_HASH,
    REFRESH_TOKEN_PREFIX,
    create_token,
    hash_password,
    hash_token,
    verify_password,
)

# Decorator
from .decorators import authenticated

# Permissions
from .permissions import (
    check_permission,
    is_org_admin,
    is_org_member,
    is_org_owner,
)

# Validators
from .validators import (
    get_and_validate_param,
    register_validator,
    validate_url_params,
)

__all__ = [
    # Context
    "AuthMethod",
    "ImpersonationContext",
    "OperatorAccessContext",
    "RequestContext",
    "UserContext",
    "OrgContext",
    "get_context",
    "set_context",
    "clear_context",
    # Decorator
    "authenticated",
    # Permissions
    "check_permission",
    "is_org_member",
    "is_org_admin",
    "is_org_owner",
    # Validators
    "register_validator",
    "validate_url_params",
    "get_and_validate_param",
    # Crypto
    "hash_password",
    "verify_password",
    "create_token",
    "hash_token",
    "API_KEY_PREFIX",
    "REFRESH_TOKEN_PREFIX",
    "DUMMY_HASH",
]
