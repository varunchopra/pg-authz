from typing import Annotated, TypeVar

from flask import request
from pydantic import AfterValidator, BaseModel, EmailStr, Field, ValidationError

from .config import Config

T = TypeVar("T", bound=BaseModel)


def _normalize_email(v: str) -> str:
    """Normalize email to lowercase."""
    return v.lower()


def _validate_password(v: str) -> str:
    """Validate password meets policy requirements."""
    # DoS protection first - reject before checking other rules
    if len(v) > 1024:
        raise ValueError("Password too long")

    if len(v) < Config.MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {Config.MIN_PASSWORD_LENGTH} characters"
        )

    # Future policies - just add checks here:
    # if not any(c.isupper() for c in v):
    #     raise ValueError("Password must contain an uppercase letter")
    # if not any(c.isdigit() for c in v):
    #     raise ValueError("Password must contain a digit")

    return v


def _validate_login_password(v: str) -> str:
    """Sanity check only - prevent DoS from extremely long passwords."""
    if len(v) > 1024:
        raise ValueError("Password too long")
    return v


# Email normalized to lowercase for consistent lookups
NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]

# Password with policy enforcement - use for signup/reset (password creation)
Password = Annotated[str, AfterValidator(_validate_password)]

# Password for login - only DoS protection, NOT policy enforcement. Keep this
# minimal: policy changes should not lock out existing users. Add new password
# rules to _validate_password instead.
LoginPassword = Annotated[str, AfterValidator(_validate_login_password)]


class SignupRequest(BaseModel):
    email: NormalizedEmail
    password: Password


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: LoginPassword


class PasswordResetRequest(BaseModel):
    email: NormalizedEmail


class PasswordResetConfirm(BaseModel):
    token: str
    password: Password


class NoteScopeConfig(BaseModel):
    """Configuration for notes access scope."""

    access: str = Field(default="none", pattern="^(none|all|selected)$")
    level: str = Field(default="read", pattern="^(read|write|admin)$")
    selected_ids: list[str] = Field(default_factory=list)


class ApiKeyScopesConfig(BaseModel):
    """Scope configuration for API key."""

    notes: NoteScopeConfig = Field(default_factory=NoteScopeConfig)


class ApiKeyRequest(BaseModel):
    name: str = Field(default="default", max_length=64)
    expires_in_days: int = Field(default=30, ge=1, le=365)
    scopes: ApiKeyScopesConfig = Field(default_factory=ApiKeyScopesConfig)


# --- Form validation helpers ---


def validate_form(model: type[T]) -> tuple[T | None, str | None]:
    """
    Validate form data against a Pydantic model.

    Returns (data, None) on success, (None, error_message) on failure.
    """
    try:
        return model.model_validate(request.form.to_dict()), None
    except ValidationError as e:
        # Get the first human-readable error message
        err = e.errors(include_context=False)[0]
        msg = err.get("msg", "Validation failed")
        # Strip "Value error, " prefix that Pydantic adds
        if msg.startswith("Value error, "):
            msg = msg[13:]
        return None, msg
