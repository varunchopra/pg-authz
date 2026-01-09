"""Integration tests for API keys with scoped permissions."""

import hashlib
import secrets
from datetime import timedelta


def hash_key(raw_key: str) -> str:
    """Hash a raw key for storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class TestApiKeyWithScopedPermissions:
    """API keys with authz-backed scopes."""

    def test_direct_permissions(self, clients):
        """API key gets direct permission grants."""
        authn, authz, _ = clients

        user_id = authn.create_user("alice@example.com", hash_key("password123"))
        raw_key = secrets.token_urlsafe(32)
        key_id = authn.create_api_key(
            user_id,
            hash_key(raw_key),
            name="Production",
            expires_in=timedelta(days=365),
        )

        authz.grant("read", resource=("repo", "api"), subject=("api_key", key_id))
        authz.grant("write", resource=("repo", "api"), subject=("api_key", key_id))

        key_info = authn.validate_api_key(hash_key(raw_key))
        assert key_info is not None
        assert key_info["user_id"] == user_id
        assert key_info["name"] == "Production"

        assert authz.check(("api_key", key_id), "read", ("repo", "api"))
        assert authz.check(("api_key", key_id), "write", ("repo", "api"))
        assert not authz.check(("api_key", key_id), "admin", ("repo", "api"))

    def test_inherits_via_group(self, clients):
        """API key inherits permissions through group membership."""
        authn, authz, _ = clients

        user_id = authn.create_user("bob@example.com", hash_key("password"))
        raw_key = secrets.token_urlsafe(32)
        key_id = authn.create_api_key(user_id, hash_key(raw_key), name="CI/CD")

        authz.grant(
            "member", resource=("group", "ci-services"), subject=("api_key", key_id)
        )
        authz.grant(
            "deploy", resource=("env", "staging"), subject=("group", "ci-services")
        )

        assert authz.check(("api_key", key_id), "deploy", ("env", "staging"))

    def test_hierarchy_expansion(self, clients):
        """API key permissions expand via hierarchy."""
        authn, authz, _ = clients

        authz.set_hierarchy("repo", "admin", "write", "read")

        user_id = authn.create_user("carol@example.com", hash_key("password"))
        raw_key = secrets.token_urlsafe(32)
        key_id = authn.create_api_key(user_id, hash_key(raw_key), name="Admin Key")

        authz.grant("admin", resource=("repo", "core"), subject=("api_key", key_id))

        assert authz.check(("api_key", key_id), "admin", ("repo", "core"))
        assert authz.check(("api_key", key_id), "write", ("repo", "core"))
        assert authz.check(("api_key", key_id), "read", ("repo", "core"))

    def test_check_any_and_all(self, clients):
        """check_any and check_all work correctly with non-user subjects."""
        authn, authz, _ = clients

        user_id = authn.create_user("dave@example.com", hash_key("password"))
        raw_key = secrets.token_urlsafe(32)
        key_id = authn.create_api_key(user_id, hash_key(raw_key))

        authz.grant("read", resource=("doc", "spec"), subject=("api_key", key_id))
        authz.grant("comment", resource=("doc", "spec"), subject=("api_key", key_id))

        assert authz.check_any(("api_key", key_id), ["read", "write"], ("doc", "spec"))
        assert not authz.check_any(
            ("api_key", key_id), ["write", "delete"], ("doc", "spec")
        )

        assert authz.check_all(
            ("api_key", key_id), ["read", "comment"], ("doc", "spec")
        )
        assert not authz.check_all(
            ("api_key", key_id), ["read", "write"], ("doc", "spec")
        )

    def test_revoked_key_denied(self, clients):
        """Revoked API key fails validation."""
        authn, authz, _ = clients

        user_id = authn.create_user("eve@example.com", hash_key("password"))
        raw_key = secrets.token_urlsafe(32)
        key_id = authn.create_api_key(user_id, hash_key(raw_key))

        authz.grant("read", resource=("doc", "secret"), subject=("api_key", key_id))

        assert authn.validate_api_key(hash_key(raw_key)) is not None
        assert authn.revoke_api_key(key_id)
        assert authn.validate_api_key(hash_key(raw_key)) is None

    def test_expired_key_denied(self, authn):
        """Expired API key fails validation."""
        user_id = authn.create_user("frank@example.com", hash_key("password"))
        raw_key = secrets.token_urlsafe(32)

        authn.create_api_key(
            user_id, hash_key(raw_key), expires_in=timedelta(seconds=-1)
        )

        assert authn.validate_api_key(hash_key(raw_key)) is None

    def test_disabled_user_key_denied(self, authn):
        """API key for disabled user fails validation."""
        user_id = authn.create_user("grace@example.com", hash_key("password"))
        raw_key = secrets.token_urlsafe(32)
        authn.create_api_key(user_id, hash_key(raw_key))

        assert authn.validate_api_key(hash_key(raw_key)) is not None
        authn.disable_user(user_id)
        assert authn.validate_api_key(hash_key(raw_key)) is None


class TestRealWorldScenarios:
    """End-to-end scenarios."""

    def test_scoped_api_key_flow(self, clients):
        """API key with scoped permissions and rate limits."""
        authn, authz, config = clients

        owner_id = authn.create_user("owner@acme.com", hash_key("secure-password"))
        raw_key = secrets.token_urlsafe(32)
        key_id = authn.create_api_key(
            owner_id, hash_key(raw_key), name="Production API Key"
        )

        authz.grant(
            "read", resource=("resource_type", "customers"), subject=("api_key", key_id)
        )
        authz.grant(
            "create", resource=("resource_type", "charges"), subject=("api_key", key_id)
        )
        config.set(f"limits/api_key/{key_id}", {"requests_per_minute": 100})

        def handle_request(key_hash: str, action: str, resource_type: str) -> dict:
            key_info = authn.validate_api_key(key_hash)
            if not key_info:
                return {"status": 401}

            if not authz.check(
                ("api_key", key_info["key_id"]),
                action,
                ("resource_type", resource_type),
            ):
                return {"status": 403}

            limits = config.get_value(f"limits/api_key/{key_info['key_id']}")
            return {
                "status": 200,
                "rate_limit": limits["requests_per_minute"] if limits else 60,
            }

        assert handle_request(hash_key(raw_key), "read", "customers")["status"] == 200
        assert handle_request(hash_key(raw_key), "create", "charges")["status"] == 200
        assert handle_request(hash_key(raw_key), "delete", "customers")["status"] == 403
        assert (
            handle_request(hash_key("wrong-key"), "read", "customers")["status"] == 401
        )

    def test_fine_grained_token(self, clients):
        """Token with subset of user's permissions."""
        authn, authz, _ = clients

        dev_id = authn.create_user("dev@example.com", hash_key("password"))

        # User has admin on multiple repos
        authz.grant("admin", resource=("repo", "frontend"), subject=("user", dev_id))
        authz.grant("admin", resource=("repo", "backend"), subject=("user", dev_id))

        # Token only gets limited access to one repo
        raw_token = secrets.token_urlsafe(32)
        token_id = authn.create_api_key(dev_id, hash_key(raw_token))
        authz.grant(
            "read", resource=("repo", "frontend"), subject=("api_key", token_id)
        )
        authz.grant(
            "write", resource=("repo", "frontend"), subject=("api_key", token_id)
        )

        # Token is limited
        assert authz.check(("api_key", token_id), "write", ("repo", "frontend"))
        assert not authz.check(("api_key", token_id), "admin", ("repo", "frontend"))
        assert not authz.check(("api_key", token_id), "read", ("repo", "backend"))

        # User still has full access
        assert authz.check(("user", dev_id), "admin", ("repo", "frontend"))
        assert authz.check(("user", dev_id), "admin", ("repo", "backend"))


class TestServiceToServiceAuth:
    """Service-to-service authentication."""

    def test_service_identity(self, authz):
        """Services as subjects with direct grants."""
        authz.grant(
            "read", resource=("database", "users"), subject=("service", "api-gateway")
        )
        authz.grant(
            "write", resource=("queue", "events"), subject=("service", "api-gateway")
        )

        assert authz.check(("service", "api-gateway"), "read", ("database", "users"))
        assert authz.check(("service", "api-gateway"), "write", ("queue", "events"))
        assert not authz.check(
            ("service", "api-gateway"), "delete", ("database", "users")
        )

    def test_service_in_group(self, authz):
        """Services inherit permissions through groups."""
        authz.grant(
            "member",
            resource=("group", "internal-services"),
            subject=("service", "billing"),
        )
        authz.grant(
            "member",
            resource=("group", "internal-services"),
            subject=("service", "shipping"),
        )
        authz.grant(
            "read",
            resource=("database", "orders"),
            subject=("group", "internal-services"),
        )

        assert authz.check(("service", "billing"), "read", ("database", "orders"))
        assert authz.check(("service", "shipping"), "read", ("database", "orders"))
