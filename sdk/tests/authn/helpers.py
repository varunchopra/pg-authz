"""Test helpers for authn - direct table access for test setup/teardown."""

from datetime import timedelta


class AuthnTestHelpers:
    """
    Direct table access for test setup/teardown that bypasses the SDK.

    Use cases:
    - Inserting expired/invalid data that SDK would reject
    - Counting records for verification
    - Testing edge cases that require direct table manipulation
    """

    def __init__(self, cursor, namespace: str):
        self.cursor = cursor
        self.namespace = namespace
        self.cursor.execute("SELECT authn.set_tenant(%s)", (namespace,))

    def count_users(self) -> int:
        """Count users in namespace."""
        self.cursor.execute(
            "SELECT COUNT(*) FROM authn.users WHERE namespace = %s",
            (self.namespace,),
        )
        return self.cursor.fetchone()[0]

    def count_sessions(self, user_id: str | None = None) -> int:
        """Count sessions, optionally filtered by user."""
        if user_id:
            self.cursor.execute(
                "SELECT COUNT(*) FROM authn.sessions WHERE namespace = %s AND user_id = %s::uuid",
                (self.namespace, user_id),
            )
        else:
            self.cursor.execute(
                "SELECT COUNT(*) FROM authn.sessions WHERE namespace = %s",
                (self.namespace,),
            )
        return self.cursor.fetchone()[0]

    def count_tokens(
        self, user_id: str | None = None, token_type: str | None = None
    ) -> int:
        """Count tokens, optionally filtered."""
        conditions = ["namespace = %s"]
        params: list = [self.namespace]

        if user_id:
            conditions.append("user_id = %s::uuid")
            params.append(user_id)
        if token_type:
            conditions.append("token_type = %s")
            params.append(token_type)

        self.cursor.execute(
            f"SELECT COUNT(*) FROM authn.tokens WHERE {' AND '.join(conditions)}",
            tuple(params),
        )
        return self.cursor.fetchone()[0]

    def insert_expired_session(
        self,
        user_id: str,
        token_hash: str,
        expired_ago: timedelta = timedelta(hours=1),
    ) -> str:
        """Insert an already-expired session for testing."""
        self.cursor.execute(
            """
            INSERT INTO authn.sessions (namespace, user_id, token_hash, expires_at)
            VALUES (%s, %s::uuid, %s, now() - %s)
            RETURNING id
            """,
            (self.namespace, user_id, token_hash, expired_ago),
        )
        return str(self.cursor.fetchone()[0])

    def insert_expired_token(
        self,
        user_id: str,
        token_hash: str,
        token_type: str,
        expired_ago: timedelta = timedelta(hours=1),
    ) -> str:
        """Insert an already-expired token for testing."""
        self.cursor.execute(
            """
            INSERT INTO authn.tokens (namespace, user_id, token_hash, token_type, expires_at)
            VALUES (%s, %s::uuid, %s, %s, now() - %s)
            RETURNING id
            """,
            (self.namespace, user_id, token_hash, token_type, expired_ago),
        )
        return str(self.cursor.fetchone()[0])

    def get_user_raw(self, user_id: str) -> dict | None:
        """Get user including password_hash for testing."""
        self.cursor.execute(
            "SELECT * FROM authn.users WHERE namespace = %s AND id = %s::uuid",
            (self.namespace, user_id),
        )
        result = self.cursor.fetchone()
        if result is None:
            return None
        columns = [desc[0] for desc in self.cursor.description]
        return dict(zip(columns, result))
