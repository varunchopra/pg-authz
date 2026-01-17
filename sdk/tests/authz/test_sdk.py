"""
SDK core behavior tests for postkit/authz.

Tests the AuthzClient SDK through its public API - the "happy path" tests.
Edge cases and specialized functionality are in dedicated test files.
"""


class TestGrantAndCheck:
    """Core grant/check behavior."""

    def test_grant_allows_access(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check(("user", "alice"), "read", ("doc", "1"))

    def test_no_grant_means_no_access(self, authz):
        assert not authz.check(("user", "alice"), "read", ("doc", "1"))

    def test_grant_is_idempotent(self, authz):
        id1 = authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        id2 = authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert id1 == id2

    def test_different_permissions_are_independent(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check(("user", "alice"), "read", ("doc", "1"))
        assert not authz.check(("user", "alice"), "write", ("doc", "1"))


class TestRevoke:
    """Revocation behavior."""

    def test_revoke_removes_access(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        assert authz.check(("user", "alice"), "read", ("doc", "1"))

        authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        assert not authz.check(("user", "alice"), "read", ("doc", "1"))

    def test_revoke_group_membership(self, authz):
        authz.grant("write", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "bob"))
        assert authz.check(("user", "bob"), "write", ("doc", "1"))

        authz.revoke("member", resource=("team", "eng"), subject=("user", "bob"))
        assert not authz.check(("user", "bob"), "write", ("doc", "1"))

    def test_revoke_direct_keeps_group_access(self, authz):
        # Alice has access via team AND direct grant
        authz.grant("read", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        # Revoke direct grant
        authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))

        # Still has access via team
        assert authz.check(("user", "alice"), "read", ("doc", "1"))

    def test_revoke_nonexistent_returns_false(self, authz):
        """Revoking a permission that doesn't exist returns False."""
        result = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        assert result is False

    def test_revoke_existing_returns_true(self, authz):
        """Revoking an existing permission returns True."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        result = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        assert result is True

    def test_double_revoke_returns_false(self, authz):
        """Revoking twice returns False the second time."""
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        first = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))
        second = authz.revoke("read", resource=("doc", "1"), subject=("user", "alice"))

        assert first is True
        assert second is False


class TestBatchChecks:
    """Batch permission checks (check_any, check_all)."""

    def test_check_any_true_if_one_matches(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check_any(("user", "alice"), ["write", "read"], ("doc", "1"))

    def test_check_any_false_if_none_match(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert not authz.check_any(("user", "alice"), ["write", "admin"], ("doc", "1"))

    def test_check_all_true_if_all_match(self, authz):
        authz.set_hierarchy("doc", "admin", "write", "read")
        authz.grant("admin", resource=("doc", "1"), subject=("user", "alice"))

        assert authz.check_all(
            ("user", "alice"), ["admin", "write", "read"], ("doc", "1")
        )

    def test_check_all_false_if_any_missing(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        assert not authz.check_all(("user", "alice"), ["read", "write"], ("doc", "1"))

    def test_check_all_empty_list_returns_true(self, authz):
        # Vacuous truth: user has all zero required permissions
        assert authz.check_all(("user", "alice"), [], ("doc", "1"))

    def test_check_any_empty_list_returns_false(self, authz):
        # No permissions to check means none match
        assert not authz.check_any(("user", "alice"), [], ("doc", "1"))


class TestAudit:
    """Audit and listing operations."""

    def test_explain_explains_direct_grant(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))

        explanations = authz.explain(("user", "alice"), "read", ("doc", "1"))

        assert len(explanations) == 1
        assert "DIRECT" in explanations[0]

    def test_explain_explains_group_membership(self, authz):
        authz.grant("write", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))

        explanations = authz.explain(("user", "alice"), "write", ("doc", "1"))

        assert len(explanations) >= 1
        assert any("GROUP" in exp for exp in explanations)

    def test_explain_explains_hierarchy(self, authz):
        authz.set_hierarchy("doc", "admin", "read")
        authz.grant("admin", resource=("doc", "1"), subject=("user", "alice"))

        explanations = authz.explain(("user", "alice"), "read", ("doc", "1"))

        assert any("HIERARCHY" in exp for exp in explanations)

    def test_explain_returns_no_access_message(self, authz):
        explanations = authz.explain(("user", "alice"), "read", ("doc", "1"))

        assert len(explanations) == 1
        assert "NO ACCESS" in explanations[0]

    def test_list_subjects_lists_subjects(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "1"), subject=("user", "bob"))

        subjects = authz.list_subjects("read", ("doc", "1"))

        assert ("user", "alice") in subjects
        assert ("user", "bob") in subjects

    def test_list_subjects_includes_group_members(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("team", "eng"))
        authz.grant("member", resource=("team", "eng"), subject=("user", "alice"))

        subjects = authz.list_subjects("read", ("doc", "1"))

        assert ("user", "alice") in subjects

    def test_list_resources_lists_resources(self, authz):
        authz.grant("read", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("read", resource=("doc", "2"), subject=("user", "alice"))

        docs = authz.list_resources(("user", "alice"), "doc", "read")

        assert "1" in docs
        assert "2" in docs


class TestSubjectGrants:
    """Subject grant listing and revocation (e.g., for API keys)."""

    def test_list_grants_returns_grants(self, authz):
        """list_grants returns all grants for a subject."""
        authz.grant("view", resource=("note", "1"), subject=("api_key", "key-123"))
        authz.grant("edit", resource=("note", "2"), subject=("api_key", "key-123"))

        grants = authz.list_grants(("api_key", "key-123"))

        assert len(grants) == 2
        resources = [g["resource"] for g in grants]
        assert ("note", "1") in resources
        assert ("note", "2") in resources

    def test_list_grants_filters_by_resource_type(self, authz):
        """list_grants can filter by resource type."""
        authz.grant("view", resource=("note", "1"), subject=("api_key", "key-123"))
        authz.grant("view", resource=("doc", "2"), subject=("api_key", "key-123"))

        grants = authz.list_grants(("api_key", "key-123"), resource_type="note")

        assert len(grants) == 1
        assert grants[0]["resource"] == ("note", "1")

    def test_list_grants_returns_empty_for_no_grants(self, authz):
        """list_grants returns empty list when no grants exist."""
        grants = authz.list_grants(("api_key", "nonexistent"))
        assert grants == []

    def test_revoke_all_grants_removes_all(self, authz):
        """revoke_all_grants removes all grants for a subject."""
        authz.grant("view", resource=("note", "1"), subject=("api_key", "key-123"))
        authz.grant("edit", resource=("note", "2"), subject=("api_key", "key-123"))

        count = authz.revoke_all_grants(("api_key", "key-123"))

        assert count == 2
        assert authz.list_grants(("api_key", "key-123")) == []

    def test_revoke_all_grants_filters_by_resource_type(self, authz):
        """revoke_all_grants can filter by resource type."""
        authz.grant("view", resource=("note", "1"), subject=("api_key", "key-123"))
        authz.grant("view", resource=("doc", "2"), subject=("api_key", "key-123"))

        count = authz.revoke_all_grants(("api_key", "key-123"), resource_type="note")

        assert count == 1
        grants = authz.list_grants(("api_key", "key-123"))
        assert len(grants) == 1
        assert grants[0]["resource"] == ("doc", "2")

    def test_revoke_all_grants_returns_zero_for_no_grants(self, authz):
        """revoke_all_grants returns 0 when no grants exist."""
        count = authz.revoke_all_grants(("api_key", "nonexistent"))
        assert count == 0

    def test_revoke_all_grants_doesnt_affect_other_subjects(self, authz):
        """revoke_all_grants only affects the specified subject."""
        authz.grant("view", resource=("note", "1"), subject=("api_key", "key-123"))
        authz.grant("view", resource=("note", "1"), subject=("api_key", "key-456"))

        authz.revoke_all_grants(("api_key", "key-123"))

        # key-456 should still have access
        assert authz.check(("api_key", "key-456"), "view", ("note", "1"))


class TestViewerContext:
    """Tests for set_viewer/clear_viewer."""

    def test_set_viewer(self, authz):
        authz.set_viewer(("user", "alice"))
        authz.cursor.execute(
            "SELECT current_setting('authz.viewer_type', true), current_setting('authz.viewer_id', true)"
        )
        result = authz.cursor.fetchone()
        assert result[0] == "user"
        assert result[1] == "alice"
        assert authz._viewer == ("user", "alice")

    def test_clear_viewer(self, authz):
        authz.set_viewer(("user", "alice"))
        authz.clear_viewer()
        authz.cursor.execute(
            "SELECT current_setting('authz.viewer_type', true), current_setting('authz.viewer_id', true)"
        )
        result = authz.cursor.fetchone()
        assert result[0] == ""
        assert result[1] == ""
        assert authz._viewer is None


class TestResourceGrants:
    """Tests for resource grant operations (revoke_resource_grants)."""

    def test_revoke_resource_grants_removes_all_on_resource(self, authz):
        """revoke_resource_grants removes all grants ON a resource."""
        authz.grant("owner", resource=("note", "1"), subject=("user", "alice"))
        authz.grant("edit", resource=("note", "1"), subject=("user", "bob"))
        authz.grant("view", resource=("note", "1"), subject=("user", "charlie"))

        count = authz.revoke_resource_grants(("note", "1"))

        assert count == 3
        assert not authz.check(("user", "alice"), "owner", ("note", "1"))
        assert not authz.check(("user", "bob"), "edit", ("note", "1"))
        assert not authz.check(("user", "charlie"), "view", ("note", "1"))

    def test_revoke_resource_grants_filters_by_permission(self, authz):
        """revoke_resource_grants can filter by permission."""
        authz.grant("owner", resource=("note", "1"), subject=("user", "alice"))
        authz.grant("view", resource=("note", "1"), subject=("user", "bob"))
        authz.grant("view", resource=("note", "1"), subject=("user", "charlie"))

        count = authz.revoke_resource_grants(("note", "1"), permission="view")

        assert count == 2
        # Owner grant should still exist
        assert authz.check(("user", "alice"), "owner", ("note", "1"))
        # View grants should be gone
        assert not authz.check(("user", "bob"), "view", ("note", "1"))
        assert not authz.check(("user", "charlie"), "view", ("note", "1"))

    def test_revoke_resource_grants_doesnt_affect_other_resources(self, authz):
        """revoke_resource_grants only affects the specified resource."""
        authz.grant("view", resource=("note", "1"), subject=("user", "alice"))
        authz.grant("view", resource=("note", "2"), subject=("user", "alice"))

        authz.revoke_resource_grants(("note", "1"))

        # note:2 should still be accessible
        assert authz.check(("user", "alice"), "view", ("note", "2"))

    def test_revoke_resource_grants_returns_zero_for_no_grants(self, authz):
        """revoke_resource_grants returns 0 when no grants exist."""
        count = authz.revoke_resource_grants(("note", "nonexistent"))
        assert count == 0


class TestTransferGrant:
    """Tests for atomic grant transfer between subjects."""

    def test_transfer_grant_moves_permission(self, authz):
        """transfer_grant moves permission from one subject to another."""
        authz.grant("owner", resource=("org", "1"), subject=("user", "alice"))

        result = authz.transfer_grant(
            "owner",
            resource=("org", "1"),
            from_subject=("user", "alice"),
            to_subject=("user", "bob"),
        )

        assert result is True
        assert not authz.check(("user", "alice"), "owner", ("org", "1"))
        assert authz.check(("user", "bob"), "owner", ("org", "1"))

    def test_transfer_grant_returns_false_if_source_not_found(self, authz):
        """transfer_grant returns False if source doesn't have the grant."""
        result = authz.transfer_grant(
            "owner",
            resource=("org", "1"),
            from_subject=("user", "alice"),
            to_subject=("user", "bob"),
        )

        assert result is False

    def test_transfer_grant_overwrites_existing(self, authz):
        """transfer_grant works even if target already has some grant."""
        authz.grant("owner", resource=("org", "1"), subject=("user", "alice"))
        authz.grant("member", resource=("org", "1"), subject=("user", "bob"))

        authz.transfer_grant(
            "owner",
            resource=("org", "1"),
            from_subject=("user", "alice"),
            to_subject=("user", "bob"),
        )

        # Bob should now have owner (member is separate)
        assert authz.check(("user", "bob"), "owner", ("org", "1"))


class TestListSubjectsWithFilter:
    """Tests for list_subjects with subject_type filter."""

    def test_list_subjects_filters_by_type(self, authz):
        """list_subjects can filter by subject_type."""
        authz.grant("view", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("view", resource=("doc", "1"), subject=("user", "bob"))
        authz.grant("view", resource=("doc", "1"), subject=("api_key", "key-1"))

        users = authz.list_subjects("view", ("doc", "1"), subject_type="user")
        api_keys = authz.list_subjects("view", ("doc", "1"), subject_type="api_key")

        assert len(users) == 2
        assert all(s[0] == "user" for s in users)
        assert len(api_keys) == 1
        assert all(s[0] == "api_key" for s in api_keys)

    def test_list_subjects_without_filter_returns_all(self, authz):
        """list_subjects without subject_type returns all types."""
        authz.grant("view", resource=("doc", "1"), subject=("user", "alice"))
        authz.grant("view", resource=("doc", "1"), subject=("api_key", "key-1"))

        subjects = authz.list_subjects("view", ("doc", "1"))

        assert len(subjects) == 2
        types = {s[0] for s in subjects}
        assert types == {"user", "api_key"}

    def test_list_subjects_with_filter_and_pagination(self, authz):
        """list_subjects filters work with pagination."""
        for i in range(5):
            authz.grant("view", resource=("doc", "1"), subject=("user", f"user{i}"))
            authz.grant("view", resource=("doc", "1"), subject=("api_key", f"key{i}"))

        page1 = authz.list_subjects("view", ("doc", "1"), subject_type="user", limit=2)
        page2 = authz.list_subjects(
            "view", ("doc", "1"), subject_type="user", limit=2, cursor=page1[-1]
        )

        assert len(page1) == 2
        assert len(page2) == 2
        all_subjects = page1 + page2
        assert all(s[0] == "user" for s in all_subjects)
