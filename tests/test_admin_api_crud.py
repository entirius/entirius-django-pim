# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
CRUD tests for PIM Admin API.

Covers write operations (POST, PATCH, DELETE) across all resource types:
- Permission enforcement for write endpoints
- FeatureSet CRUD lifecycle
- Feature CRUD lifecycle
- Attribute CRUD lifecycle (composite key)
- AttributesGroup CRUD lifecycle
- FeatureSet bulk feature management (add / remove)

URL prefix: /api/pim/admin/
"""

import pytest

# ============================================================================
# Write Permission Tests
# ============================================================================


@pytest.mark.django_db
class TestWritePermissions:
    """Write operations require admin authentication."""

    def test_unauthenticated_post_feature_set_returns_401(self, api_client):
        response = api_client.post("/api/pim/admin/feature-sets/", {"idx": "test-set"}, format="json")
        assert response.status_code == 401

    def test_regular_user_post_feature_set_returns_403(self, api_client, regular_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        response = api_client.post("/api/pim/admin/feature-sets/", {"idx": "test-set"}, format="json")
        assert response.status_code == 403

    def test_unauthenticated_patch_feature_set_returns_401(self, api_client):
        response = api_client.patch("/api/pim/admin/feature-sets/nonexistent/", {"name": "x"}, format="json")
        assert response.status_code == 401

    def test_unauthenticated_delete_feature_set_returns_401(self, api_client):
        response = api_client.delete("/api/pim/admin/feature-sets/nonexistent/")
        assert response.status_code == 401

    def test_unauthenticated_post_feature_returns_401(self, api_client):
        response = api_client.post(
            "/api/pim/admin/features/", {"idx": "test-feat", "name_t9n": {"en": "Test"}}, format="json"
        )
        assert response.status_code == 401

    def test_regular_user_post_feature_returns_403(self, api_client, regular_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        response = api_client.post(
            "/api/pim/admin/features/", {"idx": "test-feat", "name_t9n": {"en": "Test"}}, format="json"
        )
        assert response.status_code == 403

    def test_unauthenticated_post_attribute_returns_401(self, api_client):
        response = api_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "feat", "idx": "val", "name_t9n": {"en": "Val"}},
            format="json",
        )
        assert response.status_code == 401

    def test_unauthenticated_post_attributes_group_returns_401(self, api_client):
        response = api_client.post(
            "/api/pim/admin/attributes-groups/", {"idx": "grp", "name_t9n": {"en": "Group"}}, format="json"
        )
        assert response.status_code == 401


# ============================================================================
# FeatureSet CRUD
# ============================================================================


@pytest.mark.django_db
class TestFeatureSetCRUD:
    """Full CRUD lifecycle for feature sets."""

    def test_create_feature_set_returns_201_with_data(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/feature-sets/",
            {"idx": "new-set", "name": "New Set", "desc": "A test set", "is_default": False},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["idx"] == "new-set"
        assert data["name"] == "New Set"
        assert data["feature_count"] == 0

    def test_create_feature_set_duplicate_idx_returns_400(self, authenticated_client):
        authenticated_client.post("/api/pim/admin/feature-sets/", {"idx": "dup-set"}, format="json")

        response = authenticated_client.post("/api/pim/admin/feature-sets/", {"idx": "dup-set"}, format="json")

        assert response.status_code == 400

    def test_create_feature_set_missing_idx_returns_400(self, authenticated_client):
        response = authenticated_client.post("/api/pim/admin/feature-sets/", {"name": "No IDX"}, format="json")

        assert response.status_code == 400

    def test_update_feature_set_name_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/feature-sets/", {"idx": "update-set", "name": "Original"}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/feature-sets/update-set/", {"name": "Updated Name"}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_update_feature_set_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.patch("/api/pim/admin/feature-sets/nonexistent/", {"name": "x"}, format="json")

        assert response.status_code == 404

    def test_delete_feature_set_returns_200_with_deleted_counts(self, authenticated_client):
        authenticated_client.post("/api/pim/admin/feature-sets/", {"idx": "del-set"}, format="json")

        response = authenticated_client.delete("/api/pim/admin/feature-sets/del-set/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_delete_feature_set_makes_it_unretrievable(self, authenticated_client):
        authenticated_client.post("/api/pim/admin/feature-sets/", {"idx": "gone-set"}, format="json")
        authenticated_client.delete("/api/pim/admin/feature-sets/gone-set/")

        response = authenticated_client.get("/api/pim/admin/feature-sets/gone-set/")

        assert response.status_code == 404

    def test_delete_feature_set_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.delete("/api/pim/admin/feature-sets/nonexistent/")

        assert response.status_code == 404

    def test_feature_set_crud_full_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/feature-sets/", {"idx": "lifecycle-set", "name": "Lifecycle Test"}, format="json"
        )
        assert r.status_code == 201

        # Read
        r = authenticated_client.get("/api/pim/admin/feature-sets/lifecycle-set/")
        assert r.status_code == 200
        assert r.json()["name"] == "Lifecycle Test"

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/feature-sets/lifecycle-set/", {"name": "Updated Name"}, format="json"
        )
        assert r.status_code == 200

        # Verify update persisted
        r = authenticated_client.get("/api/pim/admin/feature-sets/lifecycle-set/")
        assert r.json()["name"] == "Updated Name"

        # Delete
        r = authenticated_client.delete("/api/pim/admin/feature-sets/lifecycle-set/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get("/api/pim/admin/feature-sets/lifecycle-set/")
        assert r.status_code == 404


# ============================================================================
# Feature CRUD
# ============================================================================


@pytest.mark.django_db
class TestFeatureCRUD:
    """Full CRUD lifecycle for features."""

    def test_create_feature_returns_201_with_data(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/features/",
            {
                "idx": "test-color",
                "name_t9n": {"en": "Color", "pl": "Kolor"},
                "scope": 3,
                "feature_type": 7,
                "is_filterable": True,
            },
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["idx"] == "test-color"
        assert data["scope"] == 3
        assert data["feature_type"] == 7
        assert data["is_filterable"] is True

    def test_create_feature_duplicate_idx_returns_400(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "dup-feat", "name_t9n": {"en": "Dup"}}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "dup-feat", "name_t9n": {"en": "Dup"}}, format="json"
        )

        assert response.status_code == 400

    def test_create_feature_missing_idx_returns_400(self, authenticated_client):
        response = authenticated_client.post("/api/pim/admin/features/", {"name_t9n": {"en": "No IDX"}}, format="json")

        assert response.status_code == 400

    def test_create_feature_missing_name_t9n_returns_400(self, authenticated_client):
        response = authenticated_client.post("/api/pim/admin/features/", {"idx": "no-name"}, format="json")

        assert response.status_code == 400

    def test_update_feature_returns_200_with_updated_data(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "update-feat", "name_t9n": {"en": "Original"}}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/features/update-feat/",
            {"name_t9n": {"en": "Updated", "pl": "Zaktualizowany"}, "is_filterable": True},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["is_filterable"] is True

    def test_update_feature_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.patch(
            "/api/pim/admin/features/nonexistent/", {"name_t9n": {"en": "x"}}, format="json"
        )

        assert response.status_code == 404

    def test_delete_feature_returns_200_with_deleted_counts(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "del-feat", "name_t9n": {"en": "To Delete"}}, format="json"
        )

        response = authenticated_client.delete("/api/pim/admin/features/del-feat/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_delete_feature_makes_it_unretrievable(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "gone-feat", "name_t9n": {"en": "Gone"}}, format="json"
        )
        authenticated_client.delete("/api/pim/admin/features/gone-feat/")

        response = authenticated_client.get("/api/pim/admin/features/gone-feat/")

        assert response.status_code == 404

    def test_delete_feature_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.delete("/api/pim/admin/features/nonexistent/")

        assert response.status_code == 404

    def test_feature_crud_full_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "lifecycle-feat", "name_t9n": {"en": "Lifecycle Feature"}, "scope": 3},
            format="json",
        )
        assert r.status_code == 201
        assert r.json()["scope"] == 3

        # Read
        r = authenticated_client.get("/api/pim/admin/features/lifecycle-feat/")
        assert r.status_code == 200

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/features/lifecycle-feat/", {"is_comparable": True}, format="json"
        )
        assert r.status_code == 200
        assert r.json()["is_comparable"] is True

        # Delete
        r = authenticated_client.delete("/api/pim/admin/features/lifecycle-feat/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get("/api/pim/admin/features/lifecycle-feat/")
        assert r.status_code == 404

    def test_create_feature_with_exclude_from_inheritance_flag(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "excl-inherit-feat", "name_t9n": {"en": "Excluded Feature"}, "exclude_from_inheritance": True},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["exclude_from_inheritance"] is True

    def test_update_feature_exclude_from_inheritance_flag(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "toggle-inherit-feat", "name_t9n": {"en": "Toggle Inherit"}},
            format="json",
        )

        # Verify default is False
        r = authenticated_client.get("/api/pim/admin/features/toggle-inherit-feat/")
        assert r.json()["exclude_from_inheritance"] is False

        # Update to True
        response = authenticated_client.patch(
            "/api/pim/admin/features/toggle-inherit-feat/", {"exclude_from_inheritance": True}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["exclude_from_inheritance"] is True


# ============================================================================
# Attribute CRUD (composite key: feature_idx + idx)
# ============================================================================


@pytest.mark.django_db
class TestAttributeCRUD:
    """Full CRUD lifecycle for attributes (composite key)."""

    @pytest.fixture(autouse=True)
    def parent_feature(self, db):
        """Create the parent feature used across all attribute tests."""
        from tests.factories import FeatureFactory

        FeatureFactory(idx="attr-test-feature", name_t9n={"en": "Attr Test Feature"})

    def test_create_attribute_returns_201_with_data(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/attributes/",
            {
                "feature_idx": "attr-test-feature",
                "idx": "test-val",
                "name_t9n": {"en": "Test Value", "pl": "Wartość Testowa"},
                "display_order": 10,
            },
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["feature_idx"] == "attr-test-feature"
        assert data["idx"] == "test-val"
        assert data["display_order"] == 10

    def test_create_attribute_duplicate_composite_key_returns_400(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "attr-test-feature", "idx": "dup-val", "name_t9n": {"en": "Dup"}},
            format="json",
        )

        response = authenticated_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "attr-test-feature", "idx": "dup-val", "name_t9n": {"en": "Dup"}},
            format="json",
        )

        assert response.status_code == 400

    def test_create_attribute_missing_feature_idx_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/attributes/", {"idx": "no-feature", "name_t9n": {"en": "No Feature"}}, format="json"
        )

        assert response.status_code == 400

    def test_create_attribute_missing_name_t9n_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/attributes/", {"feature_idx": "attr-test-feature", "idx": "no-name"}, format="json"
        )

        assert response.status_code == 400

    def test_create_attribute_nonexistent_feature_returns_404(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "ghost-feature", "idx": "val", "name_t9n": {"en": "Val"}},
            format="json",
        )

        assert response.status_code == 404

    def test_update_attribute_returns_200_with_updated_data(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "attr-test-feature", "idx": "update-val", "name_t9n": {"en": "Original Value"}},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/attributes/attr-test-feature/update-val/",
            {"name_t9n": {"en": "Updated Value"}, "display_order": 999},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["display_order"] == 999

    def test_update_attribute_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.patch(
            "/api/pim/admin/attributes/attr-test-feature/nonexistent/", {"display_order": 1}, format="json"
        )

        assert response.status_code == 404

    def test_delete_attribute_returns_200_with_deleted_counts(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "attr-test-feature", "idx": "del-val", "name_t9n": {"en": "To Delete"}},
            format="json",
        )

        response = authenticated_client.delete("/api/pim/admin/attributes/attr-test-feature/del-val/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_delete_attribute_makes_it_unretrievable(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "attr-test-feature", "idx": "gone-val", "name_t9n": {"en": "Gone"}},
            format="json",
        )
        authenticated_client.delete("/api/pim/admin/attributes/attr-test-feature/gone-val/")

        response = authenticated_client.get("/api/pim/admin/attributes/attr-test-feature/gone-val/")

        assert response.status_code == 404

    def test_delete_attribute_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.delete("/api/pim/admin/attributes/attr-test-feature/nonexistent/")

        assert response.status_code == 404

    def test_attribute_crud_full_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/attributes/",
            {
                "feature_idx": "attr-test-feature",
                "idx": "lifecycle-val",
                "name_t9n": {"en": "Lifecycle Value"},
                "display_order": 50,
            },
            format="json",
        )
        assert r.status_code == 201
        assert r.json()["display_order"] == 50

        # Read via composite key
        r = authenticated_client.get("/api/pim/admin/attributes/attr-test-feature/lifecycle-val/")
        assert r.status_code == 200
        assert r.json()["idx"] == "lifecycle-val"

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/attributes/attr-test-feature/lifecycle-val/", {"display_order": 75}, format="json"
        )
        assert r.status_code == 200
        assert r.json()["display_order"] == 75

        # Delete
        r = authenticated_client.delete("/api/pim/admin/attributes/attr-test-feature/lifecycle-val/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get("/api/pim/admin/attributes/attr-test-feature/lifecycle-val/")
        assert r.status_code == 404


# ============================================================================
# AttributesGroup CRUD
# ============================================================================


@pytest.mark.django_db
class TestAttributesGroupCRUD:
    """Full CRUD lifecycle for attributes groups."""

    def test_create_attributes_group_returns_201_with_data(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/attributes-groups/",
            {"idx": "warm-colors", "name_t9n": {"en": "Warm Colors", "pl": "Ciepłe Kolory"}},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["idx"] == "warm-colors"
        assert data["attribute_count"] == 0

    def test_create_attributes_group_duplicate_idx_returns_400(self, authenticated_client):
        """AttributesGroup.idx has unique constraint -- duplicates are rejected."""
        authenticated_client.post(
            "/api/pim/admin/attributes-groups/", {"idx": "dup-group", "name_t9n": {"en": "Dup"}}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/attributes-groups/", {"idx": "dup-group", "name_t9n": {"en": "Dup"}}, format="json"
        )

        assert response.status_code == 400

    def test_create_attributes_group_missing_idx_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/attributes-groups/", {"name_t9n": {"en": "No IDX"}}, format="json"
        )

        assert response.status_code == 400

    def test_create_attributes_group_missing_name_t9n_returns_400(self, authenticated_client):
        response = authenticated_client.post("/api/pim/admin/attributes-groups/", {"idx": "no-name"}, format="json")

        assert response.status_code == 400

    def test_update_attributes_group_returns_200_with_updated_data(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/attributes-groups/", {"idx": "update-group", "name_t9n": {"en": "Original"}}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/attributes-groups/update-group/",
            {"name_t9n": {"en": "Updated", "pl": "Zaktualizowany"}},
            format="json",
        )

        assert response.status_code == 200

    def test_update_attributes_group_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.patch(
            "/api/pim/admin/attributes-groups/nonexistent/", {"name_t9n": {"en": "x"}}, format="json"
        )

        assert response.status_code == 404

    def test_delete_attributes_group_returns_200_with_deleted_counts(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/attributes-groups/", {"idx": "del-group", "name_t9n": {"en": "To Delete"}}, format="json"
        )

        response = authenticated_client.delete("/api/pim/admin/attributes-groups/del-group/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_delete_attributes_group_makes_it_unretrievable(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/attributes-groups/", {"idx": "gone-group", "name_t9n": {"en": "Gone"}}, format="json"
        )
        authenticated_client.delete("/api/pim/admin/attributes-groups/gone-group/")

        response = authenticated_client.get("/api/pim/admin/attributes-groups/gone-group/")

        assert response.status_code == 404

    def test_delete_attributes_group_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.delete("/api/pim/admin/attributes-groups/nonexistent/")

        assert response.status_code == 404

    def test_attributes_group_crud_full_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/attributes-groups/",
            {"idx": "lifecycle-group", "name_t9n": {"en": "Lifecycle Group"}},
            format="json",
        )
        assert r.status_code == 201

        # Read
        r = authenticated_client.get("/api/pim/admin/attributes-groups/lifecycle-group/")
        assert r.status_code == 200
        assert r.json()["idx"] == "lifecycle-group"

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/attributes-groups/lifecycle-group/", {"name_t9n": {"en": "Updated Group"}}, format="json"
        )
        assert r.status_code == 200

        # Delete
        r = authenticated_client.delete("/api/pim/admin/attributes-groups/lifecycle-group/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get("/api/pim/admin/attributes-groups/lifecycle-group/")
        assert r.status_code == 404


# ============================================================================
# FeatureSet Bulk Feature Operations
# ============================================================================


@pytest.mark.django_db
class TestFeatureSetBulkOperations:
    """Bulk add / remove features within a feature set."""

    @pytest.fixture(autouse=True)
    def setup_set_and_features(self, db):
        """Create one feature set and three features for use across all bulk tests."""
        from tests.factories import FeatureFactory, FeatureSetFactory

        FeatureSetFactory(idx="bulk-set", name="Bulk Test Set")
        for i in range(3):
            FeatureFactory(idx=f"bulk-feat-{i}", name_t9n={"en": f"Bulk Feature {i}"}, scope=3)

    def test_bulk_add_features_returns_201(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {
                "features": [
                    {"feature_idx": "bulk-feat-0"},
                    {"feature_idx": "bulk-feat-1", "position": 100},
                    {"feature_idx": "bulk-feat-2"},
                ]
            },
            format="json",
        )
        assert response.status_code == 201

    def test_bulk_add_features_response_contains_expected_fields(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {"features": [{"feature_idx": "bulk-feat-0"}]},
            format="json",
        )

        assert response.status_code == 201
        items = response.json()
        assert len(items) == 1
        assert "position" in items[0]
        assert "feature" in items[0]
        assert items[0]["feature"]["idx"] == "bulk-feat-0"

    def test_bulk_add_duplicate_feature_returns_400(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {"features": [{"feature_idx": "bulk-feat-0"}]},
            format="json",
        )

        response = authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {"features": [{"feature_idx": "bulk-feat-0"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_bulk_add_nonexistent_feature_returns_404(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {"features": [{"feature_idx": "ghost-feature"}]},
            format="json",
        )

        assert response.status_code == 404

    def test_bulk_add_to_nonexistent_set_returns_404(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/feature-sets/ghost-set/features/",
            {"features": [{"feature_idx": "bulk-feat-0"}]},
            format="json",
        )

        assert response.status_code == 404

    def test_bulk_remove_features_returns_200_with_removed_count(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {"features": [{"feature_idx": "bulk-feat-0"}, {"feature_idx": "bulk-feat-1"}]},
            format="json",
        )

        response = authenticated_client.delete(
            "/api/pim/admin/feature-sets/bulk-set/features/", data={"feature_idxs": ["bulk-feat-0"]}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["removed"] == 1

    def test_bulk_remove_multiple_features(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {
                "features": [
                    {"feature_idx": "bulk-feat-0"},
                    {"feature_idx": "bulk-feat-1"},
                    {"feature_idx": "bulk-feat-2"},
                ]
            },
            format="json",
        )

        response = authenticated_client.delete(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            data={"feature_idxs": ["bulk-feat-0", "bulk-feat-1"]},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["removed"] == 2

    def test_bulk_remove_nonpresent_features_is_idempotent(self, authenticated_client):
        """Removing features not in the set returns 200 with count 0."""
        response = authenticated_client.delete(
            "/api/pim/admin/feature-sets/bulk-set/features/", data={"feature_idxs": ["bulk-feat-0"]}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["removed"] == 0

    def test_bulk_remove_from_nonexistent_set_returns_404(self, authenticated_client):
        response = authenticated_client.delete(
            "/api/pim/admin/feature-sets/ghost-set/features/", data={"feature_idxs": ["bulk-feat-0"]}, format="json"
        )

        assert response.status_code == 404

    def test_bulk_add_positions_reflected_in_features_list(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {
                "features": [
                    {"feature_idx": "bulk-feat-0", "position": 10},
                    {"feature_idx": "bulk-feat-1", "position": 20},
                    {"feature_idx": "bulk-feat-2", "position": 30},
                ]
            },
            format="json",
        )

        response = authenticated_client.get("/api/pim/admin/feature-sets/bulk-set/features/")

        assert response.status_code == 200
        data = response.json()
        positions = [item["position"] for item in data["results"]]
        assert positions == sorted(positions)

    def test_list_features_in_set_reflects_removed_features(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {"features": [{"feature_idx": "bulk-feat-0"}, {"feature_idx": "bulk-feat-1"}]},
            format="json",
        )
        authenticated_client.delete(
            "/api/pim/admin/feature-sets/bulk-set/features/", data={"feature_idxs": ["bulk-feat-0"]}, format="json"
        )

        response = authenticated_client.get("/api/pim/admin/feature-sets/bulk-set/features/")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["feature"]["idx"] == "bulk-feat-1"

    def test_feature_count_on_set_increases_after_bulk_add(self, authenticated_client):
        r = authenticated_client.get("/api/pim/admin/feature-sets/bulk-set/")
        initial_count = r.json()["feature_count"]

        authenticated_client.post(
            "/api/pim/admin/feature-sets/bulk-set/features/",
            {"features": [{"feature_idx": "bulk-feat-0"}, {"feature_idx": "bulk-feat-1"}]},
            format="json",
        )

        r = authenticated_client.get("/api/pim/admin/feature-sets/bulk-set/")

        assert r.json()["feature_count"] == initial_count + 2


# ============================================================================
# Product CRUD
# ============================================================================


@pytest.mark.django_db
class TestProductCRUD:
    """Full CRUD lifecycle for products (channel-scoped)."""

    @pytest.fixture(autouse=True)
    def setup_channel_and_feature_set(self, authenticated_client):
        """Create a channel and feature set for product tests."""
        from tests.factories import ChannelFactory, FeatureSetFactory

        self.channel = ChannelFactory(idx="test-shop")
        self.feature_set = FeatureSetFactory(idx="test-set", name="Test Set")

    def test_create_product_returns_201(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {
                "sku": "NEW-PROD-001",
                "feature_set_idx": "test-set",
                "visibility": 4,
                "is_enabled": True,
                "product_class": 1,
            },
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "NEW-PROD-001"
        assert data["visibility"] == 4
        assert data["is_enabled"] is True
        assert data["feature_set_idx"] == "test-set"

    def test_create_product_duplicate_sku_same_channel_returns_400(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "DUP-SKU", "feature_set_idx": "test-set"}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "DUP-SKU", "feature_set_idx": "test-set"}, format="json"
        )

        assert response.status_code == 400

    def test_create_product_same_sku_different_channel_reuses_real_product(self, authenticated_client):
        from tests.factories import ChannelFactory

        ChannelFactory(idx="other-shop", name="Other Shop")

        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "SHARED-SKU", "feature_set_idx": "test-set"}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/other-shop/products/", {"sku": "SHARED-SKU", "feature_set_idx": "test-set"}, format="json"
        )

        assert response.status_code == 201
        assert response.json()["sku"] == "SHARED-SKU"

    def test_update_product_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {"sku": "UPD-PROD", "feature_set_idx": "test-set", "visibility": 4, "is_enabled": True},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/UPD-PROD/", {"visibility": 2, "is_enabled": False}, format="json"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["visibility"] == 2
        assert data["is_enabled"] is False

    def test_delete_product_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "DEL-PROD", "feature_set_idx": "test-set"}, format="json"
        )

        response = authenticated_client.delete("/api/pim/admin/test-shop/products/DEL-PROD/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_delete_product_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.delete("/api/pim/admin/test-shop/products/NONEXISTENT/")

        assert response.status_code == 404

    def test_product_crud_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {"sku": "LIFECYCLE-PROD", "feature_set_idx": "test-set", "is_enabled": True},
            format="json",
        )
        assert r.status_code == 201

        # Read
        r = authenticated_client.get("/api/pim/admin/test-shop/products/LIFECYCLE-PROD/")
        assert r.status_code == 200
        assert r.json()["sku"] == "LIFECYCLE-PROD"

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/LIFECYCLE-PROD/", {"is_enabled": False}, format="json"
        )
        assert r.status_code == 200
        assert r.json()["is_enabled"] is False

        # Verify update persisted
        r = authenticated_client.get("/api/pim/admin/test-shop/products/LIFECYCLE-PROD/")
        assert r.json()["is_enabled"] is False

        # Delete
        r = authenticated_client.delete("/api/pim/admin/test-shop/products/LIFECYCLE-PROD/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get("/api/pim/admin/test-shop/products/LIFECYCLE-PROD/")
        assert r.status_code == 404

    def test_bulk_update_products_returns_200(self, authenticated_client):
        for sku in ("BULK-1", "BULK-2", "BULK-3"):
            authenticated_client.post(
                "/api/pim/admin/test-shop/products/",
                {"sku": sku, "feature_set_idx": "test-set", "is_enabled": True},
                format="json",
            )

        response = authenticated_client.post(
            "/api/pim/admin/test-shop/products/bulk/",
            {"skus": ["BULK-1", "BULK-2", "BULK-3"], "is_enabled": False},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["updated"] == 3

    def test_bulk_update_enable_multiple_products(self, authenticated_client):
        for sku in ("ENABLE-1", "ENABLE-2"):
            authenticated_client.post(
                "/api/pim/admin/test-shop/products/",
                {"sku": sku, "feature_set_idx": "test-set", "is_enabled": False},
                format="json",
            )

        response = authenticated_client.post(
            "/api/pim/admin/test-shop/products/bulk/",
            {"skus": ["ENABLE-1", "ENABLE-2"], "is_enabled": True, "visibility": 4},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["updated"] == 2

        # Verify changes persisted
        r = authenticated_client.get("/api/pim/admin/test-shop/products/ENABLE-1/")
        assert r.json()["is_enabled"] is True
        assert r.json()["visibility"] == 4

    def test_update_product_categories(self, authenticated_client):
        from tests.factories import ProductCategoryFactory

        ProductCategoryFactory(idx="cat-a", shop=self.channel, name_t9n={"en": "Cat A"}, url_key_t9n={"en": "cat-a"})
        ProductCategoryFactory(idx="cat-b", shop=self.channel, name_t9n={"en": "Cat B"}, url_key_t9n={"en": "cat-b"})

        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "CAT-PROD", "feature_set_idx": "test-set"}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/CAT-PROD/", {"category_idxs": ["cat-a", "cat-b"]}, format="json"
        )

        assert response.status_code == 200
        assert len(response.json()["categories"]) == 2

    def test_patch_weight_updates(self, authenticated_client):
        """PATCH with weight value updates the RealProduct weight."""
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "WEIGHT-PROD", "feature_set_idx": "test-set"}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/WEIGHT-PROD/", {"weight": "5.00"}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["weight"] == "5.00"

    def test_patch_clear_weight(self, authenticated_client):
        """PATCH with weight=null clears the RealProduct weight."""
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {"sku": "CLR-WEIGHT", "feature_set_idx": "test-set", "weight": "10.00"},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/CLR-WEIGHT/", {"weight": None}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["weight"] is None

    def test_patch_clear_ean(self, authenticated_client):
        """PATCH with ean=null clears the RealProduct EAN."""
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {"sku": "CLR-EAN", "feature_set_idx": "test-set", "ean": "1234567890123"},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/CLR-EAN/", {"ean": None}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["ean"] is None

    def test_patch_empty_payload_noop(self, authenticated_client):
        """PATCH with empty payload does not change the product."""
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {"sku": "NOOP-PROD", "feature_set_idx": "test-set", "visibility": 4, "is_enabled": True},
            format="json",
        )

        response = authenticated_client.patch("/api/pim/admin/test-shop/products/NOOP-PROD/", {}, format="json")

        assert response.status_code == 200
        data = response.json()
        assert data["visibility"] == 4
        assert data["is_enabled"] is True

    def test_patch_visibility(self, authenticated_client):
        """PATCH visibility changes the product visibility."""
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {"sku": "VIS-PROD", "feature_set_idx": "test-set", "visibility": 4},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/VIS-PROD/", {"visibility": 1}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["visibility"] == 1

    def test_patch_is_enabled_false(self, authenticated_client):
        """PATCH is_enabled=false disables the product."""
        authenticated_client.post(
            "/api/pim/admin/test-shop/products/",
            {"sku": "DIS-PROD", "feature_set_idx": "test-set", "is_enabled": True},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/DIS-PROD/", {"is_enabled": False}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["is_enabled"] is False

    def test_patch_attributes_select(self, authenticated_client):
        """PATCH with SELECT attribute updates the attribute value."""
        from tests.factories import AttributeFactory, FeatureFactory, FeatureInFeatureSetFactory

        feature = FeatureFactory(idx="color-select", feature_type=7, scope=3)
        FeatureInFeatureSetFactory(feature_set=self.feature_set, feature=feature)
        attr = AttributeFactory(feature=feature, idx="red")

        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "ATTR-SEL", "feature_set_idx": "test-set"}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/ATTR-SEL/",
            {"attributes": [{"feature_idx": "color-select", "attribute_idx": attr.idx}]},
            format="json",
        )

        assert response.status_code == 200
        attrs = response.json()["attributes"]
        color_attr = next(a for a in attrs if a["feature_idx"] == "color-select")
        assert color_attr["attribute_idx"] == "red"

    def test_patch_attributes_decimal(self, authenticated_client):
        """PATCH with DECIMAL attribute updates the value."""
        from tests.factories import FeatureFactory, FeatureInFeatureSetFactory

        feature = FeatureFactory(idx="test-decimal", feature_type=2, scope=3)
        FeatureInFeatureSetFactory(feature_set=self.feature_set, feature=feature)

        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "ATTR-DEC", "feature_set_idx": "test-set"}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/ATTR-DEC/",
            {"attributes": [{"feature_idx": "test-decimal", "value_decimal": "42.50"}]},
            format="json",
        )

        assert response.status_code == 200
        attrs = response.json()["attributes"]
        dec_attr = next(a for a in attrs if a["feature_idx"] == "test-decimal")
        assert dec_attr["value_decimal"] == "42.500000"

    def test_patch_categories_full_replace(self, authenticated_client):
        """PATCH with category_idxs replaces all category assignments."""
        from tests.factories import ProductCategoryFactory

        ProductCategoryFactory(
            idx="rep-cat-a", shop=self.channel, name_t9n={"en": "Rep A"}, url_key_t9n={"en": "rep-a"}
        )
        ProductCategoryFactory(
            idx="rep-cat-b", shop=self.channel, name_t9n={"en": "Rep B"}, url_key_t9n={"en": "rep-b"}
        )

        authenticated_client.post(
            "/api/pim/admin/test-shop/products/", {"sku": "REP-CAT", "feature_set_idx": "test-set"}, format="json"
        )

        # Assign both categories
        authenticated_client.patch(
            "/api/pim/admin/test-shop/products/REP-CAT/", {"category_idxs": ["rep-cat-a", "rep-cat-b"]}, format="json"
        )

        # Replace with only one
        response = authenticated_client.patch(
            "/api/pim/admin/test-shop/products/REP-CAT/", {"category_idxs": ["rep-cat-b"]}, format="json"
        )

        assert response.status_code == 200
        cats = response.json()["categories"]
        assert len(cats) == 1
        assert cats[0]["idx"] == "rep-cat-b"


# ============================================================================
# Category CRUD
# ============================================================================


@pytest.mark.django_db
class TestCategoryCRUD:
    """Full CRUD lifecycle for categories (channel-scoped)."""

    @pytest.fixture(autouse=True)
    def setup_channel(self, authenticated_client):
        """Create a channel for category tests."""
        from tests.factories import ChannelFactory

        self.channel = ChannelFactory(idx="cat-shop")

    def test_create_category_returns_201(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/",
            {
                "idx": "new-cat",
                "name_t9n": {"en": "New Category", "pl": "Nowa Kategoria"},
                "is_active": True,
                "is_in_menu": True,
            },
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["idx"] == "new-cat"
        assert data["name_t9n"]["en"] == "New Category"
        assert data["is_active"] is True
        assert data["tree_deep"] == 0
        assert data["product_count"] == 0

    def test_list_exposes_url_key_resolved_by_channel_language(self, authenticated_client):
        """List returns url_key for the channel's default language (the slug Matrix routes by); falls back to idx."""
        from tests.factories import ProductCategoryFactory

        # idx != url_key, slug present for the channel's default language
        ProductCategoryFactory(
            idx="fabric-options-all",
            shop=self.channel,
            name_t9n={"PL": "All Fabrics"},
            url_key_t9n={"PL": "all-fabrics"},
        )
        # no slug for the channel language -> url_key must fall back to idx
        ProductCategoryFactory(idx="sofas", shop=self.channel, name_t9n={"PL": "Sofas"}, url_key_t9n={})

        response = authenticated_client.get("/api/pim/admin/cat-shop/categories/")

        assert response.status_code == 200
        by_idx = {c["idx"]: c for c in response.json()["results"]}
        assert by_idx["fabric-options-all"]["url_key"] == "all-fabrics"
        assert by_idx["sofas"]["url_key"] == "sofas"  # fallback to idx when no slug for the language

    def test_create_category_duplicate_idx_returns_400(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/", {"idx": "dup-cat", "name_t9n": {"en": "Dup"}}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/", {"idx": "dup-cat", "name_t9n": {"en": "Dup"}}, format="json"
        )

        assert response.status_code == 400

    def test_update_category_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/", {"idx": "upd-cat", "name_t9n": {"en": "Original"}}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/cat-shop/categories/upd-cat/",
            {"name_t9n": {"en": "Updated Name"}, "is_active": False},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["name_t9n"]["en"] == "Updated Name"
        assert response.json()["is_active"] is False

    def test_update_category_parent_circular_returns_400(self, authenticated_client):
        # Create parent and child
        authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/", {"idx": "parent-cat", "name_t9n": {"en": "Parent"}}, format="json"
        )
        authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/",
            {"idx": "child-cat", "name_t9n": {"en": "Child"}, "parent_category_idx": "parent-cat"},
            format="json",
        )

        # Try to make parent a child of its own child -> circular
        response = authenticated_client.patch(
            "/api/pim/admin/cat-shop/categories/parent-cat/", {"parent_category_idx": "child-cat"}, format="json"
        )

        assert response.status_code == 400

    def test_delete_category_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/", {"idx": "del-cat", "name_t9n": {"en": "To Delete"}}, format="json"
        )

        response = authenticated_client.delete("/api/pim/admin/cat-shop/categories/del-cat/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_delete_category_cascades_subcategories(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/",
            {"idx": "cascade-parent", "name_t9n": {"en": "Parent"}},
            format="json",
        )
        authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/",
            {"idx": "cascade-child", "name_t9n": {"en": "Child"}, "parent_category_idx": "cascade-parent"},
            format="json",
        )

        response = authenticated_client.delete("/api/pim/admin/cat-shop/categories/cascade-parent/")

        assert response.status_code == 200

        # Verify child is also gone
        r = authenticated_client.get("/api/pim/admin/cat-shop/categories/cascade-child/")
        assert r.status_code == 404

    def test_category_crud_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/cat-shop/categories/",
            {"idx": "lifecycle-cat", "name_t9n": {"en": "Lifecycle Cat"}, "is_active": True},
            format="json",
        )
        assert r.status_code == 201

        # Read
        r = authenticated_client.get("/api/pim/admin/cat-shop/categories/lifecycle-cat/")
        assert r.status_code == 200
        assert r.json()["idx"] == "lifecycle-cat"

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/cat-shop/categories/lifecycle-cat/",
            {"name_t9n": {"en": "Updated Cat"}, "is_in_menu": False},
            format="json",
        )
        assert r.status_code == 200
        assert r.json()["is_in_menu"] is False

        # Delete
        r = authenticated_client.delete("/api/pim/admin/cat-shop/categories/lifecycle-cat/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get("/api/pim/admin/cat-shop/categories/lifecycle-cat/")
        assert r.status_code == 404


# ============================================================================
# Feature Scope Protection
# ============================================================================


@pytest.fixture
def system_feature(db):
    """Create a SYSTEM-scoped feature (scope=1) with a reserved idx."""
    from django_pim.models import Feature, FeatureScopeEnum, FeatureTypeEnum

    return Feature.objects.create(
        idx="name",
        scope=FeatureScopeEnum.SYSTEM,
        feature_type=FeatureTypeEnum.VARCHAR255_T9N,
        name_t9n={"en": "Name", "pl": "Nazwa"},
        is_required=False,
    )


@pytest.fixture
def bu_feature(db):
    """Create a BUSINESS_UNIT-scoped feature (scope=3)."""
    from django_pim.models import Feature, FeatureScopeEnum, FeatureTypeEnum

    return Feature.objects.create(
        idx="color",
        scope=FeatureScopeEnum.BUSINESS_UNIT,
        feature_type=FeatureTypeEnum.SELECT,
        name_t9n={"en": "Color", "pl": "Kolor"},
    )


@pytest.mark.django_db
class TestFeatureScopeProtection:
    """SYSTEM features are protected from dangerous modifications."""

    def test_create_feature_system_scope_rejected(self, authenticated_client):
        """POST with scope=1 (SYSTEM) is rejected at schema level."""
        response = authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "new-system", "name_t9n": {"en": "Bad"}, "scope": 1}, format="json"
        )
        assert response.status_code == 400

    def test_update_system_feature_scope_rejected(self, authenticated_client, system_feature):
        """Cannot change scope of a SYSTEM feature."""
        response = authenticated_client.patch(
            f"/api/pim/admin/features/{system_feature.idx}/", {"scope": 3}, format="json"
        )
        assert response.status_code == 400

    def test_update_system_feature_type_rejected(self, authenticated_client, system_feature):
        """Cannot change feature_type of a SYSTEM feature."""
        response = authenticated_client.patch(
            f"/api/pim/admin/features/{system_feature.idx}/", {"feature_type": 2}, format="json"
        )
        assert response.status_code == 400

    def test_update_system_feature_required_rejected(self, authenticated_client, system_feature):
        """Cannot change is_required of a SYSTEM feature."""
        response = authenticated_client.patch(
            f"/api/pim/admin/features/{system_feature.idx}/", {"is_required": True}, format="json"
        )
        assert response.status_code == 400

    def test_update_system_feature_name_t9n_allowed(self, authenticated_client, system_feature):
        """Translations (name_t9n) on SYSTEM features are editable."""
        response = authenticated_client.patch(
            f"/api/pim/admin/features/{system_feature.idx}/",
            {"name_t9n": {"en": "Product Name", "pl": "Nazwa produktu"}},
            format="json",
        )
        assert response.status_code == 200

    def test_update_system_feature_visibility_allowed(self, authenticated_client, system_feature):
        """Visibility flags on SYSTEM features are editable."""
        response = authenticated_client.patch(
            f"/api/pim/admin/features/{system_feature.idx}/", {"is_visible": False}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["is_visible"] is False

    def test_update_system_feature_display_order_allowed(self, authenticated_client, system_feature):
        """Display order on SYSTEM features is editable."""
        response = authenticated_client.patch(
            f"/api/pim/admin/features/{system_feature.idx}/", {"display_order": 5}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["display_order"] == 5

    def test_delete_system_feature_rejected(self, authenticated_client, system_feature):
        """Cannot delete a SYSTEM feature."""
        response = authenticated_client.delete(f"/api/pim/admin/features/{system_feature.idx}/")
        assert response.status_code == 400

    def test_update_non_system_scope_to_system_rejected(self, authenticated_client, bu_feature):
        """Cannot change a BUSINESS_UNIT feature's scope to SYSTEM."""
        response = authenticated_client.patch(f"/api/pim/admin/features/{bu_feature.idx}/", {"scope": 1}, format="json")
        assert response.status_code == 400

    def test_is_system_flag_true_for_system_feature(self, authenticated_client, system_feature):
        """GET response includes is_system=true for SYSTEM features."""
        response = authenticated_client.get(f"/api/pim/admin/features/{system_feature.idx}/")
        assert response.status_code == 200
        assert response.json()["is_system"] is True

    def test_is_system_flag_false_for_bu_feature(self, authenticated_client, bu_feature):
        """GET response includes is_system=false for BUSINESS_UNIT features."""
        response = authenticated_client.get(f"/api/pim/admin/features/{bu_feature.idx}/")
        assert response.status_code == 200
        assert response.json()["is_system"] is False


@pytest.mark.django_db
class TestGlobalScopeDeprecation:
    """GLOBAL scope (2) is deprecated and blocked in create/update."""

    def test_create_feature_global_scope_rejected(self, authenticated_client):
        """POST with scope=2 (GLOBAL) is rejected at schema level."""
        response = authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "new-global", "name_t9n": {"en": "Bad"}, "scope": 2}, format="json"
        )
        assert response.status_code == 400

    def test_update_feature_to_global_scope_rejected(self, authenticated_client, bu_feature):
        """Cannot change a feature's scope to GLOBAL."""
        response = authenticated_client.patch(f"/api/pim/admin/features/{bu_feature.idx}/", {"scope": 2}, format="json")
        assert response.status_code == 400


# ============================================================================
# HTML Attribute Values
# ============================================================================


@pytest.mark.django_db
class TestHTMLAttributeValues:
    """HTML content roundtrips through TEXT and TEXT_T9N attributes."""

    @pytest.fixture(autouse=True)
    def setup_channel_and_product(self, db):
        from tests.factories import ChannelFactory, FeatureFactory, FeatureInFeatureSetFactory, FeatureSetFactory

        self.channel = ChannelFactory(idx="html-shop")
        self.feature_set = FeatureSetFactory(idx="html-set", name="HTML Set")

        self.text_feature = FeatureFactory(idx="html-text", feature_type=5, scope=3)
        FeatureInFeatureSetFactory(feature_set=self.feature_set, feature=self.text_feature)

        self.text_t9n_feature = FeatureFactory(idx="html-text-t9n", feature_type=6, scope=3)
        FeatureInFeatureSetFactory(feature_set=self.feature_set, feature=self.text_t9n_feature)

        from tests.factories import ProductFactory

        ProductFactory(shop=self.channel, feature_set=self.feature_set, real_product__sku="HTML-PROD")

    def test_text_attribute_html_roundtrip(self, authenticated_client):
        """TEXT (type 5) stores and returns HTML content unchanged."""
        html = "<p>Bold <strong>text</strong> and <em>italic</em></p>"

        response = authenticated_client.patch(
            "/api/pim/admin/html-shop/products/HTML-PROD/",
            {"attributes": [{"feature_idx": "html-text", "value_txt": html}]},
            format="json",
        )
        assert response.status_code == 200

        response = authenticated_client.get("/api/pim/admin/html-shop/products/HTML-PROD/")
        assert response.status_code == 200
        attr = next(a for a in response.json()["attributes"] if a["feature_idx"] == "html-text")
        assert attr["value_txt"] == html

    def test_text_t9n_attribute_html_roundtrip(self, authenticated_client):
        """TEXT_T9N (type 6) stores and returns HTML per language."""
        html_en = "<h2>Features</h2><ul><li>Durable</li><li>Lightweight</li></ul>"
        html_pl = "<h2>Cechy</h2><ul><li>Trwaly</li><li>Lekki</li></ul>"

        response = authenticated_client.patch(
            "/api/pim/admin/html-shop/products/HTML-PROD/",
            {"attributes": [{"feature_idx": "html-text-t9n", "value_txt_t9n": {"en": html_en, "pl": html_pl}}]},
            format="json",
        )
        assert response.status_code == 200

        response = authenticated_client.get("/api/pim/admin/html-shop/products/HTML-PROD/")
        assert response.status_code == 200
        attr = next(a for a in response.json()["attributes"] if a["feature_idx"] == "html-text-t9n")
        assert attr["value_txt_t9n"]["en"] == html_en
        assert attr["value_txt_t9n"]["pl"] == html_pl

    def test_update_html_attribute_preserves_tags(self, authenticated_client):
        """Updating from simple to complex HTML preserves all tags."""
        simple_html = "<p>Simple text</p>"
        authenticated_client.patch(
            "/api/pim/admin/html-shop/products/HTML-PROD/",
            {"attributes": [{"feature_idx": "html-text", "value_txt": simple_html}]},
            format="json",
        )

        complex_html = (
            '<h1>Title</h1><p>Paragraph with <a href="https://example.com">link</a>'
            " and <strong>bold</strong></p>"
            "<blockquote>A quote</blockquote>"
            "<ol><li>First</li><li>Second</li></ol>"
        )
        response = authenticated_client.patch(
            "/api/pim/admin/html-shop/products/HTML-PROD/",
            {"attributes": [{"feature_idx": "html-text", "value_txt": complex_html}]},
            format="json",
        )
        assert response.status_code == 200

        response = authenticated_client.get("/api/pim/admin/html-shop/products/HTML-PROD/")
        attr = next(a for a in response.json()["attributes"] if a["feature_idx"] == "html-text")
        assert attr["value_txt"] == complex_html


# ============================================================================
# Feature SEO + Visual Asset Flags
# ============================================================================


@pytest.mark.django_db
class TestFeatureSEOFlags:
    """Test has_visual_asset and is_seo flags on features."""

    def test_create_feature_with_has_visual_asset(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "icon-feat", "name_t9n": {"en": "Icon Feature"}, "has_visual_asset": True, "is_seo": False},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["has_visual_asset"] is True
        assert data["is_seo"] is False

    def test_create_feature_with_is_seo(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "seo-feat", "name_t9n": {"en": "SEO Feature"}, "has_visual_asset": False, "is_seo": True},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["has_visual_asset"] is False
        assert data["is_seo"] is True

    def test_create_feature_defaults_flags_to_false(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "default-flags-feat", "name_t9n": {"en": "Default Flags"}},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["has_visual_asset"] is False
        assert data["is_seo"] is False

    def test_update_feature_has_visual_asset(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "upd-visual-feat", "name_t9n": {"en": "Visual"}}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/features/upd-visual-feat/", {"has_visual_asset": True}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["has_visual_asset"] is True

    def test_update_feature_is_seo(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "upd-seo-feat", "name_t9n": {"en": "SEO"}}, format="json"
        )

        response = authenticated_client.patch("/api/pim/admin/features/upd-seo-feat/", {"is_seo": True}, format="json")

        assert response.status_code == 200
        assert response.json()["is_seo"] is True

    def test_system_feature_meta_title_has_is_seo_after_migration(self, db):
        """Verify data migration set is_seo=True on meta_title if it exists."""
        from django_pim.models import Feature

        try:
            feature = Feature.objects.get(idx="meta_title")
            assert feature.is_seo is True
        except Feature.DoesNotExist:
            # System features only exist after CSV import / data migration
            pytest.skip("meta_title system feature not present in test DB")


# ============================================================================
# Category SEO Fields
# ============================================================================


@pytest.mark.django_db
class TestCategorySEOFields:
    """Test SEO fields on categories (noindex, nofollow, canonical_url_t9n, og_image_url)."""

    @pytest.fixture(autouse=True)
    def setup_channel(self):
        from tests.factories import ChannelFactory

        self.channel = ChannelFactory(idx="seo-shop")

    def test_create_category_with_seo_fields(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/seo-shop/categories/",
            {
                "idx": "seo-cat",
                "name_t9n": {"en": "SEO Category"},
                "noindex": True,
                "nofollow": False,
                "canonical_url_t9n": {"en": "https://example.com/seo-category"},
                "og_image_url": "https://example.com/images/seo-og.jpg",
            },
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["noindex"] is True
        assert data["nofollow"] is False
        assert data["canonical_url_t9n"]["en"] == "https://example.com/seo-category"
        assert data["og_image_url"] == "https://example.com/images/seo-og.jpg"

    def test_create_category_seo_defaults(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/seo-shop/categories/",
            {"idx": "default-seo-cat", "name_t9n": {"en": "Default SEO"}},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["noindex"] is False
        assert data["nofollow"] is False
        assert data["canonical_url_t9n"] == {}
        assert data["og_image_url"] == ""

    def test_update_category_nofollow(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/seo-shop/categories/",
            {"idx": "upd-nofollow-cat", "name_t9n": {"en": "NoFollow Cat"}},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/seo-shop/categories/upd-nofollow-cat/", {"nofollow": True}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["nofollow"] is True

    def test_update_category_canonical_url_t9n(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/seo-shop/categories/",
            {"idx": "upd-canonical-cat", "name_t9n": {"en": "Canonical Cat"}},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/seo-shop/categories/upd-canonical-cat/",
            {"canonical_url_t9n": {"en": "https://example.com/canonical", "pl": "https://example.com/pl/canonical"}},
            format="json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["canonical_url_t9n"]["en"] == "https://example.com/canonical"
        assert data["canonical_url_t9n"]["pl"] == "https://example.com/pl/canonical"

    def test_update_category_og_image_url(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/seo-shop/categories/", {"idx": "upd-og-cat", "name_t9n": {"en": "OG Cat"}}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/seo-shop/categories/upd-og-cat/",
            {"og_image_url": "https://cdn.example.com/og-image.jpg"},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["og_image_url"] == "https://cdn.example.com/og-image.jpg"

    def test_category_seo_roundtrip(self, authenticated_client):
        """Full create-read-update-read lifecycle for SEO fields."""
        # Create with SEO fields
        r = authenticated_client.post(
            "/api/pim/admin/seo-shop/categories/",
            {
                "idx": "roundtrip-seo",
                "name_t9n": {"en": "Roundtrip SEO"},
                "noindex": True,
                "nofollow": True,
                "canonical_url_t9n": {"en": "https://example.com/original"},
                "og_image_url": "https://example.com/original-og.jpg",
            },
            format="json",
        )
        assert r.status_code == 201

        # Read
        r = authenticated_client.get("/api/pim/admin/seo-shop/categories/roundtrip-seo/")
        assert r.status_code == 200
        assert r.json()["noindex"] is True

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/seo-shop/categories/roundtrip-seo/",
            {"noindex": False, "canonical_url_t9n": {"en": "https://example.com/updated"}},
            format="json",
        )
        assert r.status_code == 200
        assert r.json()["noindex"] is False
        assert r.json()["canonical_url_t9n"]["en"] == "https://example.com/updated"
        # nofollow unchanged
        assert r.json()["nofollow"] is True


class TestDescContract:
    """`desc` grounding field contract (featureset-cascade etap-01): present in responses,
    defaults to "" (FeatureSet precedent — deliberate api-response-contract deviation),
    writable via create and PATCH on all taxonomy entities."""

    @pytest.fixture(autouse=True)
    def setup_channel(self, authenticated_client):
        from tests.factories import ChannelFactory

        self.channel = ChannelFactory(idx="desc-shop")

    def test_feature_desc_roundtrip(self, authenticated_client):
        created = authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "desc-feat", "name_t9n": {"en": "F"}}, format="json"
        )
        assert created.status_code == 201
        assert created.json()["desc"] == ""  # default, never omitted

        response = authenticated_client.patch(
            "/api/pim/admin/features/desc-feat/", {"desc": "Plain colours only."}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["desc"] == "Plain colours only."

        # PATCH without desc leaves it untouched
        response = authenticated_client.patch(
            "/api/pim/admin/features/desc-feat/", {"is_filterable": True}, format="json"
        )
        assert response.json()["desc"] == "Plain colours only."

    def test_feature_create_with_desc(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "desc-feat-2", "name_t9n": {"en": "F"}, "desc": "Ground me."},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["desc"] == "Ground me."

    def test_category_desc_roundtrip(self, authenticated_client):
        created = authenticated_client.post(
            "/api/pim/admin/desc-shop/categories/", {"idx": "desc-cat", "name_t9n": {"en": "C"}}, format="json"
        )
        assert created.status_code == 201
        assert created.json()["desc"] == ""

        response = authenticated_client.patch(
            "/api/pim/admin/desc-shop/categories/desc-cat/", {"desc": "Hand tools only."}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["desc"] == "Hand tools only."

    def test_attributes_group_desc_roundtrip(self, authenticated_client):
        created = authenticated_client.post(
            "/api/pim/admin/attributes-groups/",
            {"idx": "desc-group", "name_t9n": {"en": "G"}, "desc": "Muted tones."},
            format="json",
        )
        assert created.status_code == 201
        assert created.json()["desc"] == "Muted tones."

        response = authenticated_client.patch(
            "/api/pim/admin/attributes-groups/desc-group/", {"desc": "Loud tones."}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["desc"] == "Loud tones."

    def test_attribute_desc_roundtrip(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/features/", {"idx": "desc-attr-feat", "name_t9n": {"en": "F"}}, format="json"
        )
        created = authenticated_client.post(
            "/api/pim/admin/attributes/",
            {"feature_idx": "desc-attr-feat", "idx": "desc-attr", "name_t9n": {"en": "A"}},
            format="json",
        )
        assert created.status_code == 201
        assert created.json()["desc"] == ""

        response = authenticated_client.patch(
            "/api/pim/admin/attributes/desc-attr-feat/desc-attr/", {"desc": "RAL 9010 family."}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["desc"] == "RAL 9010 family."

    def test_desc_present_on_channel_scoped_reads(self, authenticated_client):
        """Global write, channel read: `desc` must also surface on channel-scoped endpoints."""
        authenticated_client.post(
            "/api/pim/admin/features/",
            {"idx": "desc-ch-feat", "name_t9n": {"en": "F"}, "desc": "Channel read me."},
            format="json",
        )
        authenticated_client.post(
            "/api/pim/admin/desc-shop/categories/",
            {"idx": "desc-ch-cat", "name_t9n": {"en": "C"}, "desc": "Listed."},
            format="json",
        )

        feature = authenticated_client.get("/api/pim/admin/desc-shop/features/desc-ch-feat/")
        assert feature.status_code == 200
        assert feature.json()["desc"] == "Channel read me."

        listing = authenticated_client.get("/api/pim/admin/desc-shop/categories/")
        assert listing.status_code == 200
        items = {c["idx"]: c for c in listing.json()["results"]}
        assert items["desc-ch-cat"]["desc"] == "Listed."
