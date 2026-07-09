# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
CRUD tests for PIM Admin API: Product Links and Link Types.

Covers write operations (POST, PATCH, DELETE) for link-related resources:
- Permission enforcement for link type and product link endpoints
- LinkType CRUD lifecycle (global resource, idx-keyed)
- ProductLink CRUD lifecycle (channel-scoped, nested under product)

URL prefix: /api/pim/admin/
"""

import pytest

from tests.factories import (
    ChannelFactory,
    FeatureSetFactory,
    ProductFactory,
    ProductLinkTypeFactory,
    RealProductFactory,
)


@pytest.fixture
def shop(db):
    return ChannelFactory(idx="test-links-channel", name="Test Links Channel")


@pytest.fixture
def product_a(shop):
    fs = FeatureSetFactory()
    rp = RealProductFactory(sku="LINK-A")
    return ProductFactory(shop=shop, feature_set=fs, real_product=rp)


@pytest.fixture
def product_b(shop):
    fs = FeatureSetFactory()
    rp = RealProductFactory(sku="LINK-B")
    return ProductFactory(shop=shop, feature_set=fs, real_product=rp)


@pytest.fixture
def link_type(db):
    return ProductLinkTypeFactory(idx="related", name_t9n={"en": "Related Products"}, position=1)


# ============================================================================
# LinkType Auth Tests
# ============================================================================


@pytest.mark.django_db
class TestLinkTypeAuth:
    """Link type endpoints require admin authentication."""

    def test_unauthenticated_get_link_types_returns_401(self, api_client):
        response = api_client.get("/api/pim/admin/link-types/")
        assert response.status_code == 401

    def test_regular_user_post_link_type_returns_403(self, api_client, regular_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        response = api_client.post(
            "/api/pim/admin/link-types/", {"idx": "related", "name_t9n": {"en": "Related"}}, format="json"
        )
        assert response.status_code == 403

    def test_admin_get_link_types_returns_200(self, authenticated_client):
        response = authenticated_client.get("/api/pim/admin/link-types/")
        assert response.status_code == 200


# ============================================================================
# LinkType CRUD
# ============================================================================


@pytest.mark.django_db
class TestLinkTypeCRUD:
    """Full CRUD lifecycle for product link types."""

    def test_list_link_types_returns_paginated_results(self, authenticated_client):
        response = authenticated_client.get("/api/pim/admin/link-types/")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

    def test_create_link_type_returns_201_with_data(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/link-types/",
            {"idx": "test-crosssell", "name_t9n": {"en": "Cross-Sell", "pl": "Sprzedaż krzyżowa"}, "position": 2},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["idx"] == "test-crosssell"
        assert data["name_t9n"] == {"en": "Cross-Sell", "pl": "Sprzedaż krzyżowa"}
        assert data["name"] == "Cross-Sell"
        assert data["position"] == 2

    def test_create_link_type_duplicate_idx_returns_400(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/link-types/", {"idx": "dup-type", "name_t9n": {"en": "Dup"}}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/link-types/", {"idx": "dup-type", "name_t9n": {"en": "Dup"}}, format="json"
        )

        assert response.status_code == 400

    def test_create_link_type_missing_idx_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/link-types/", {"name_t9n": {"en": "No IDX"}}, format="json"
        )

        assert response.status_code == 400

    def test_retrieve_link_type_by_idx_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/link-types/",
            {"idx": "test-upsell", "name_t9n": {"en": "Up-Sell"}, "position": 3},
            format="json",
        )

        response = authenticated_client.get("/api/pim/admin/link-types/test-upsell/")

        assert response.status_code == 200
        data = response.json()
        assert data["idx"] == "test-upsell"

    def test_retrieve_link_type_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.get("/api/pim/admin/link-types/nonexistent-type/")
        assert response.status_code == 404

    def test_update_link_type_name_t9n_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/link-types/",
            {"idx": "test-navigation", "name_t9n": {"en": "Navigation"}, "position": 4},
            format="json",
        )

        response = authenticated_client.patch(
            "/api/pim/admin/link-types/test-navigation/",
            {"name_t9n": {"en": "Navigation Links", "pl": "Linki nawigacyjne"}},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["name_t9n"] == {"en": "Navigation Links", "pl": "Linki nawigacyjne"}

    def test_delete_link_type_returns_200_with_deleted_key(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/link-types/", {"idx": "del-type", "name_t9n": {"en": "To Delete"}}, format="json"
        )

        response = authenticated_client.delete("/api/pim/admin/link-types/del-type/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_link_type_crud_full_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/link-types/",
            {"idx": "lifecycle-type", "name_t9n": {"en": "Lifecycle Type"}, "position": 10},
            format="json",
        )
        assert r.status_code == 201
        assert r.json()["idx"] == "lifecycle-type"

        # Read
        r = authenticated_client.get("/api/pim/admin/link-types/lifecycle-type/")
        assert r.status_code == 200
        assert r.json()["name_t9n"] == {"en": "Lifecycle Type"}

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/link-types/lifecycle-type/",
            {"name_t9n": {"en": "Updated Type"}, "position": 99},
            format="json",
        )
        assert r.status_code == 200

        # Verify update persisted
        r = authenticated_client.get("/api/pim/admin/link-types/lifecycle-type/")
        assert r.json()["position"] == 99
        assert r.json()["name_t9n"] == {"en": "Updated Type"}

        # Delete
        r = authenticated_client.delete("/api/pim/admin/link-types/lifecycle-type/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get("/api/pim/admin/link-types/lifecycle-type/")
        assert r.status_code == 404


# ============================================================================
# ProductLink Auth Tests
# ============================================================================


@pytest.mark.django_db
class TestProductLinkAuth:
    """Product link endpoints require admin authentication."""

    def test_unauthenticated_get_product_links_returns_401(self, api_client, product_a):
        response = api_client.get("/api/pim/admin/test-links-channel/products/LINK-A/links/")
        assert response.status_code == 401

    def test_admin_get_product_links_returns_200(self, authenticated_client, product_a):
        response = authenticated_client.get("/api/pim/admin/test-links-channel/products/LINK-A/links/")
        assert response.status_code == 200


# ============================================================================
# ProductLink CRUD
# ============================================================================


@pytest.mark.django_db
class TestProductLinkCRUD:
    """Full CRUD lifecycle for product links."""

    def test_list_links_returns_empty_for_product_with_no_links(self, authenticated_client, product_a):
        response = authenticated_client.get("/api/pim/admin/test-links-channel/products/LINK-A/links/")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_create_link_returns_201_with_data(self, authenticated_client, product_a, product_b, link_type):
        response = authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 1},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["linked_product"]["sku"] == "LINK-B"
        assert data["link_type_idx"] == "related"
        assert data["position"] == 1
        assert "pk" in data

    def test_create_self_link_returns_400(self, authenticated_client, product_a, link_type):
        response = authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-A", "link_type_idx": "related", "position": 1},
            format="json",
        )

        assert response.status_code == 400

    def test_create_duplicate_link_returns_400(self, authenticated_client, product_a, product_b, link_type):
        authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 1},
            format="json",
        )

        response = authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 2},
            format="json",
        )

        assert response.status_code == 400

    def test_retrieve_link_by_pk_returns_200(self, authenticated_client, product_a, product_b, link_type):
        create_response = authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 1},
            format="json",
        )
        pk = create_response.json()["pk"]

        response = authenticated_client.get(f"/api/pim/admin/test-links-channel/products/LINK-A/links/{pk}/")

        assert response.status_code == 200
        assert response.json()["pk"] == pk

    def test_retrieve_nonexistent_link_returns_404(self, authenticated_client, product_a):
        response = authenticated_client.get("/api/pim/admin/test-links-channel/products/LINK-A/links/99999/")
        assert response.status_code == 404

    def test_update_link_position_returns_200(self, authenticated_client, product_a, product_b, link_type):
        create_response = authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 1},
            format="json",
        )
        pk = create_response.json()["pk"]

        response = authenticated_client.patch(
            f"/api/pim/admin/test-links-channel/products/LINK-A/links/{pk}/", {"position": 99}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["position"] == 99

    def test_delete_link_returns_200_with_deleted_key(self, authenticated_client, product_a, product_b, link_type):
        create_response = authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 1},
            format="json",
        )
        pk = create_response.json()["pk"]

        response = authenticated_client.delete(f"/api/pim/admin/test-links-channel/products/LINK-A/links/{pk}/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_filter_links_by_link_type_returns_matching_results(
        self, authenticated_client, product_a, product_b, link_type
    ):
        crosssell_type = ProductLinkTypeFactory(
            idx="crosssell-filter", name_t9n={"en": "Cross-Sell Filter"}, position=2
        )

        authenticated_client.post(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/",
            {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 1},
            format="json",
        )

        response = authenticated_client.get(
            "/api/pim/admin/test-links-channel/products/LINK-A/links/", {"link_type": crosssell_type.idx}
        )

        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_product_link_crud_full_lifecycle(self, authenticated_client, product_a, product_b, link_type):
        base_url = "/api/pim/admin/test-links-channel/products/LINK-A/links/"

        # Create
        r = authenticated_client.post(
            base_url, {"linked_product_sku": "LINK-B", "link_type_idx": "related", "position": 5}, format="json"
        )
        assert r.status_code == 201
        pk = r.json()["pk"]

        # Read
        r = authenticated_client.get(f"{base_url}{pk}/")
        assert r.status_code == 200
        assert r.json()["position"] == 5

        # Update
        r = authenticated_client.patch(f"{base_url}{pk}/", {"position": 50}, format="json")
        assert r.status_code == 200

        # Verify update persisted
        r = authenticated_client.get(f"{base_url}{pk}/")
        assert r.json()["position"] == 50

        # Delete
        r = authenticated_client.delete(f"{base_url}{pk}/")
        assert r.status_code == 200

        # Verify deleted
        r = authenticated_client.get(f"{base_url}{pk}/")
        assert r.status_code == 404


class TestLinkTypeDescContract:
    """`desc` grounding field on link types (featureset-cascade etap-01)."""

    def test_link_type_desc_roundtrip(self, authenticated_client):
        created = authenticated_client.post(
            "/api/pim/admin/link-types/", {"idx": "desc-lt", "name_t9n": {"en": "Fits with"}}, format="json"
        )
        assert created.status_code == 201
        assert created.json()["desc"] == ""  # default, never omitted

        response = authenticated_client.patch(
            "/api/pim/admin/link-types/desc-lt/", {"desc": "Accessories that fit; never substitutes."}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["desc"] == "Accessories that fit; never substitutes."
