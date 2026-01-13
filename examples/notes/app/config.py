import os
import secrets


class Config:
    APP_NAME = os.environ.get("APP_NAME", "Notes")
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/app")
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    # Namespace/tenant for authn and authz
    NAMESPACE = os.environ.get("POSTKIT_NAMESPACE", "default")
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI_API = os.environ.get(
        "GOOGLE_REDIRECT_URI_API", "http://localhost:5000/api/auth/google/callback"
    )
    GOOGLE_REDIRECT_URI_VIEW = os.environ.get(
        "GOOGLE_REDIRECT_URI_VIEW", "http://localhost:5000/auth/google/callback"
    )
    MIN_PASSWORD_LENGTH = 8
    # Token expiry settings
    ACCESS_TOKEN_EXPIRES_HOURS = int(os.environ.get("ACCESS_TOKEN_EXPIRES_HOURS", "1"))
    REFRESH_TOKEN_EXPIRES_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRES_DAYS", "30"))
