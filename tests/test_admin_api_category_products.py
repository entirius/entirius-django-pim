# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for product position management within categories.

Covers:
- Authentication (401/403/200)
- List products in category (positioned + unpositioned split)
- Search by SKU
- Pagination of unpositioned products
- Reorder (pin, unpin, reorder multiple)
- Error cases (bad category, invalid SKU)

URL prefix: /api/pim/v2/admin/
"""

import pytest

from tests.factories import (
    ChannelFactory,
    FeatureSetFactory,
    ProductCategoryFactory,
    ProductFactory,
    ProductInCategoryFactory,
    RealProductFactory,
)

BASE_URL = "/api/pim/v2/admin"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def channel(db):
    return ChannelFactory(idx="cat-prod-channel", name="Cat Prod Channel")


@pytest.fixture
def feature_set(db):
    return FeatureSetFactory()


@pytest.fixture
def category(channel):
    return ProductCategoryFactory(shop=channel, idx="test-cat-for-products")


@pytest.fixture
def products_in_category(channel, category, feature_set):
    """Create 5 products: 2 positioned, 3 unpositioned."""
    items = []
    for i in range(5):
        rp = RealProductFactory(sku=f"CAT-PROD-{i:03d}")
        product = ProductFactory(shop=channel, real_product=rp, feature_set=feature_set)
        position = i + 1 if i < 2 else 0
        pic = ProductInCategoryFactory(product=product, category=category, position=position)
        items.append(pic)
    return items


# ============================================================================
# Auth Tests
# ============================================================================


@pytest.mark.django_db
class TestCategoryProductsAuth:
    """Authentication and permission tests."""

    def test_unauthenticated_returns_401(self, api_client, channel, category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        response = api_client.get(url)
        assert response.status_code == 401

    def test_regular_user_returns_403(self, api_client, regular_token, channel, category):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        response = api_client.get(url)
        assert response.status_code == 403

    def test_admin_user_returns_200(self, authenticated_client, channel, category, products_in_category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        response = authenticated_client.get(url)
        assert response.status_code == 200

    def test_reorder_unauthenticated_returns_401(self, api_client, channel, category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = api_client.patch(url, {}, format="json")
        assert response.status_code == 401

    def test_reorder_regular_user_returns_403(self, api_client, regular_token, channel, category):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = api_client.patch(url, {"items": []}, format="json")
        assert response.status_code == 403


# ============================================================================
# List Tests
# ============================================================================


@pytest.mark.django_db
class TestCategoryProductsList:
    """Test listing products in a category."""

    def test_positioned_products_sorted_by_position(
        self, authenticated_client, channel, category, products_in_category
    ):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        response = authenticated_client.get(url)
        data = response.json()

        assert len(data["positioned"]) == 2
        positions = [p["position"] for p in data["positioned"]]
        assert positions == sorted(positions)
        assert all(p > 0 for p in positions)

    def test_unpositioned_products_returned(self, authenticated_client, channel, category, products_in_category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        response = authenticated_client.get(url)
        data = response.json()

        assert data["unpositioned_count"] == 3
        assert len(data["unpositioned"]) == 3
        assert all(p["position"] == 0 for p in data["unpositioned"])

    def test_response_has_expected_fields(self, authenticated_client, channel, category, products_in_category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        response = authenticated_client.get(url)
        data = response.json()

        assert "positioned" in data
        assert "unpositioned" in data
        assert "unpositioned_count" in data
        assert "unpositioned_next" in data
        assert "unpositioned_previous" in data

        product = data["positioned"][0]
        assert "sku" in product
        assert "name" in product
        assert "position" in product
        assert "is_enabled" in product
        assert "thumbnail_url" in product

    def test_search_filters_by_sku(self, authenticated_client, channel, category, products_in_category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/?search=CAT-PROD-002"
        response = authenticated_client.get(url)
        data = response.json()

        assert data["unpositioned_count"] == 1
        assert data["unpositioned"][0]["sku"] == "CAT-PROD-002"

    def test_empty_category_returns_empty(self, authenticated_client, channel, feature_set):
        empty_cat = ProductCategoryFactory(shop=channel, idx="empty-category")
        url = f"{BASE_URL}/{channel.idx}/categories/{empty_cat.idx}/products/"
        response = authenticated_client.get(url)
        data = response.json()

        assert data["positioned"] == []
        assert data["unpositioned"] == []
        assert data["unpositioned_count"] == 0

    def test_404_for_nonexistent_category(self, authenticated_client, channel):
        url = f"{BASE_URL}/{channel.idx}/categories/nonexistent/products/"
        response = authenticated_client.get(url)
        assert response.status_code == 404

    def test_404_for_nonexistent_channel(self, authenticated_client, category):
        url = f"{BASE_URL}/nonexistent-channel/categories/{category.idx}/products/"
        response = authenticated_client.get(url)
        assert response.status_code == 404

    def test_pagination_of_unpositioned(self, authenticated_client, channel, category, feature_set):
        """Create 30 unpositioned products, verify pagination at page_size=24."""
        for i in range(30):
            rp = RealProductFactory(sku=f"PAGE-PROD-{i:03d}")
            product = ProductFactory(shop=channel, real_product=rp, feature_set=feature_set)
            ProductInCategoryFactory(product=product, category=category, position=0)

        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/?page_size=24"
        response = authenticated_client.get(url)
        data = response.json()

        assert data["unpositioned_count"] == 30
        assert len(data["unpositioned"]) == 24
        assert data["unpositioned_next"] == 2
        assert data["unpositioned_previous"] is None

    def test_pagination_page_2(self, authenticated_client, channel, category, feature_set):
        """Create 30 unpositioned products, verify page 2."""
        for i in range(30):
            rp = RealProductFactory(sku=f"P2-PROD-{i:03d}")
            product = ProductFactory(shop=channel, real_product=rp, feature_set=feature_set)
            ProductInCategoryFactory(product=product, category=category, position=0)

        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/?page=2&page_size=24"
        response = authenticated_client.get(url)
        data = response.json()

        assert len(data["unpositioned"]) == 6
        assert data["unpositioned_next"] is None
        assert data["unpositioned_previous"] == 1


# ============================================================================
# Reorder Tests
# ============================================================================


@pytest.mark.django_db
class TestCategoryProductsReorder:
    """Test reordering products in a category."""

    def test_pin_product(self, authenticated_client, channel, category, products_in_category):
        """Set position > 0 to pin an unpositioned product."""
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = authenticated_client.patch(url, {"items": [{"sku": "CAT-PROD-002", "position": 5}]}, format="json")
        assert response.status_code == 200
        assert response.json()["reordered"] == 1

        # Verify in list
        list_url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        list_response = authenticated_client.get(list_url)
        data = list_response.json()
        positioned_skus = [p["sku"] for p in data["positioned"]]
        assert "CAT-PROD-002" in positioned_skus

    def test_unpin_product(self, authenticated_client, channel, category, products_in_category):
        """Set position = 0 to unpin a positioned product."""
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = authenticated_client.patch(url, {"items": [{"sku": "CAT-PROD-000", "position": 0}]}, format="json")
        assert response.status_code == 200

        list_url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        list_response = authenticated_client.get(list_url)
        data = list_response.json()
        positioned_skus = [p["sku"] for p in data["positioned"]]
        assert "CAT-PROD-000" not in positioned_skus

    def test_reorder_multiple(self, authenticated_client, channel, category, products_in_category):
        """Reorder multiple products at once."""
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = authenticated_client.patch(
            url,
            {
                "items": [
                    {"sku": "CAT-PROD-000", "position": 3},
                    {"sku": "CAT-PROD-001", "position": 1},
                    {"sku": "CAT-PROD-002", "position": 2},
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["reordered"] == 3

        list_url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/"
        list_response = authenticated_client.get(list_url)
        data = list_response.json()
        positioned_skus = [p["sku"] for p in data["positioned"]]
        assert positioned_skus == ["CAT-PROD-001", "CAT-PROD-002", "CAT-PROD-000"]

    def test_reorder_invalid_sku_returns_404(self, authenticated_client, channel, category, products_in_category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = authenticated_client.patch(
            url, {"items": [{"sku": "NONEXISTENT-SKU", "position": 1}]}, format="json"
        )
        assert response.status_code == 404

    def test_reorder_nonexistent_category_returns_404(self, authenticated_client, channel):
        url = f"{BASE_URL}/{channel.idx}/categories/nonexistent/products/reorder/"
        response = authenticated_client.patch(url, {"items": [{"sku": "CAT-PROD-000", "position": 1}]}, format="json")
        assert response.status_code == 404

    def test_reorder_empty_items_returns_200(self, authenticated_client, channel, category):
        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = authenticated_client.patch(url, {"items": []}, format="json")
        assert response.status_code == 200
        assert response.json()["reordered"] == 0

    def test_reorder_product_not_in_category_returns_404(self, authenticated_client, channel, category, feature_set):
        """Product exists in channel but not assigned to this category."""
        rp = RealProductFactory(sku="ORPHAN-SKU")
        ProductFactory(shop=channel, real_product=rp, feature_set=feature_set)

        url = f"{BASE_URL}/{channel.idx}/categories/{category.idx}/products/reorder/"
        response = authenticated_client.patch(url, {"items": [{"sku": "ORPHAN-SKU", "position": 1}]}, format="json")
        assert response.status_code == 404
