# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for PIM Admin API with JWT authentication.

Tests cover:
- JWT authentication and authorization
- All admin endpoints (Products, Categories, Features, etc.)
- Filtering and pagination
- Permission checks (IsAdminUser)
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from django_pim.models import AttributesGroup

User = get_user_model()


@pytest.fixture
def shop(db):
    """Create test shop."""
    from tests.factories import ShopFactory

    return ShopFactory()


@pytest.fixture
def superuser(db):
    """Create superuser."""
    user = User.objects.create_user(
        username="super", email="super@test.com", password="superpass123", is_staff=False, is_superuser=True
    )
    return user


@pytest.fixture
def superuser_token(superuser):
    """Generate JWT token for superuser."""
    refresh = RefreshToken.for_user(superuser)
    return str(refresh.access_token)


# ============================================================================
# Authentication & Authorization Tests
# ============================================================================


@pytest.mark.django_db
class TestAuthentication:
    """Test JWT authentication and IsAdminUser permission."""

    def test_unauthenticated_request_returns_401(self, api_client, shop):
        """Request without token should return 401 Unauthorized."""
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = api_client.get(url)

        assert response.status_code == 401
        assert "Authentication credentials were not provided" in str(response.data)

    def test_invalid_token_returns_401(self, api_client, shop):
        """Request with invalid token should return 401."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer invalid_token_12345")
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = api_client.get(url)

        assert response.status_code == 401

    def test_regular_user_returns_403(self, api_client, regular_token, shop):
        """Request from non-admin user should return 403 Forbidden."""
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = api_client.get(url)

        assert response.status_code == 403
        assert "do not have permission" in str(response.data)

    def test_admin_user_returns_200(self, api_client, admin_token, shop):
        """Request from admin user (is_staff=True) should succeed."""
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = api_client.get(url)

        assert response.status_code == 200

    def test_superuser_returns_200(self, api_client, superuser_token, shop):
        """Request from superuser should succeed."""
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {superuser_token}")
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = api_client.get(url)

        assert response.status_code == 200


# ============================================================================
# Product Endpoints Tests
# ============================================================================


@pytest.mark.django_db
class TestProductEndpoints:
    """Test Product admin endpoints."""

    @pytest.fixture
    def product(self, shop, db):
        """Create test product."""
        from tests.factories import ProductFactory

        return ProductFactory(shop=shop)

    def test_list_products(self, authenticated_client, shop, product):
        """Test GET /products/ returns product list."""
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Check DRF pagination format
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data
        assert len(data["results"]) > 0

        # Check product data structure
        product_data = data["results"][0]
        assert "pk" in product_data
        assert "sku" in product_data
        assert "name" in product_data
        assert "visibility" in product_data
        assert "is_enabled" in product_data
        # New enriched fields
        assert "visibility_int" in product_data
        assert "product_class" in product_data
        assert "product_class_name" in product_data
        assert "feature_set_idx" in product_data
        assert "thumbnail_url" in product_data

    def test_retrieve_product_by_sku(self, authenticated_client, shop, product):
        """Test GET /products/{sku}/ returns product details."""
        url = f"/api/pim/admin/{shop.idx}/products/{product.real_product.sku}/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["sku"] == product.real_product.sku
        assert "name" in data

    def test_list_products_with_search(self, authenticated_client, shop, product):
        """Test product search filter."""
        # Test search with SKU (which is guaranteed to exist)
        search_term = product.real_product.sku if product.real_product else "test"
        url = f"/api/pim/admin/{shop.idx}/products/?search={search_term}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        # Search should work (count >= 0)
        assert "count" in data
        assert "results" in data

    def test_list_products_with_is_enabled_filter(self, authenticated_client, shop, product):
        """Test is_enabled filter."""
        url = f"/api/pim/admin/{shop.idx}/products/?is_enabled=true"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # All returned products should be enabled
        for prod in data["results"]:
            assert prod["is_enabled"] is True

    def test_list_products_with_pagination(self, authenticated_client, shop):
        """Test pagination parameters."""
        url = f"/api/pim/admin/{shop.idx}/products/?page=1&page_size=5"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert len(data["results"]) <= 5

    def test_list_products_with_ordering(self, authenticated_client, shop):
        """Test ordering parameter."""
        url = f"/api/pim/admin/{shop.idx}/products/?ordering=-pk"
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_list_products_response_includes_product_class(self, authenticated_client, shop):
        """Product class and label are included in list response."""
        from tests.factories import ProductFactory

        ProductFactory(shop=shop, product_class=1)
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        for p in data["results"]:
            assert "product_class" in p
            assert "product_class_name" in p
            assert isinstance(p["product_class"], int)
            assert isinstance(p["product_class_name"], str)

    def test_list_products_response_includes_visibility_int(self, authenticated_client, shop):
        """visibility_int is the integer form of visibility."""
        from tests.factories import ProductFactory

        ProductFactory(shop=shop, visibility=4)
        url = f"/api/pim/admin/{shop.idx}/products/?visibility=4"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        for p in response.json()["results"]:
            assert p["visibility_int"] == 4
            assert isinstance(p["visibility"], str)

    def test_list_products_response_includes_feature_set_idx(self, authenticated_client, shop, product):
        """feature_set_idx is present in list results."""
        url = f"/api/pim/admin/{shop.idx}/products/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        for p in response.json()["results"]:
            assert "feature_set_idx" in p
            assert isinstance(p["feature_set_idx"], str)

    def test_list_products_response_includes_thumbnail_url(self, authenticated_client, shop):
        """thumbnail_url is non-null when product has a MAIN picture."""
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image as PILImage

        from django_pim.models import PictureRoleEnum, ProductPicture
        from django_pim.services import upload_picture
        from tests.factories import ProductFactory

        product_with_pic = ProductFactory(shop=shop)
        product_no_pic = ProductFactory(shop=shop)

        buf = io.BytesIO()
        PILImage.new("RGB", (10, 10), color="green").save(buf, format="PNG")
        buf.seek(0)
        img_file = SimpleUploadedFile("thumb.png", buf.read(), content_type="image/png")
        picture = upload_picture(img_file)
        ProductPicture.objects.create(
            product=product_with_pic, picture=picture, picture_role=PictureRoleEnum.MAIN, position=0
        )

        url = f"/api/pim/admin/{shop.idx}/products/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        results = response.json()["results"]
        by_sku = {r["sku"]: r for r in results}

        pic_result = by_sku[product_with_pic.sku]
        assert pic_result["thumbnail_url"] is not None

        no_pic_result = by_sku[product_no_pic.sku]
        assert no_pic_result["thumbnail_url"] is None

    def test_list_products_with_visibility_filter(self, authenticated_client, shop):
        """Filter by visibility enum value."""
        from tests.factories import ProductFactory

        ProductFactory(shop=shop, visibility=4)
        ProductFactory(shop=shop, visibility=1)

        url = f"/api/pim/admin/{shop.idx}/products/?visibility=4"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        for p in response.json()["results"]:
            assert p["visibility_int"] == 4

        url = f"/api/pim/admin/{shop.idx}/products/?visibility=1"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        for p in response.json()["results"]:
            assert p["visibility_int"] == 1

    def test_list_products_with_product_class_filter(self, authenticated_client, shop):
        """Filter by product class enum value."""
        from tests.factories import ProductFactory

        ProductFactory(shop=shop, product_class=1)
        ProductFactory(shop=shop, product_class=2)

        url = f"/api/pim/admin/{shop.idx}/products/?product_class=1"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        for p in response.json()["results"]:
            assert p["product_class"] == 1

    def test_list_products_with_category_filter(self, authenticated_client, shop):
        """Filter by category idx."""
        from django_pim.models import ProductInCategory
        from tests.factories import ProductCategoryFactory, ProductFactory

        product = ProductFactory(shop=shop)
        category = ProductCategoryFactory(shop=shop)
        ProductInCategory.objects.create(product=product, category=category)

        url = f"/api/pim/admin/{shop.idx}/products/?category={category.idx}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        skus = [p["sku"] for p in data["results"]]
        assert product.sku in skus

        # Different category should not return this product
        other_cat = ProductCategoryFactory(shop=shop)
        url = f"/api/pim/admin/{shop.idx}/products/?category={other_cat.idx}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_list_products_with_has_media_filter(self, authenticated_client, shop):
        """Filter by has_media (presence of MAIN picture)."""
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image as PILImage

        from django_pim.models import PictureRoleEnum, ProductPicture
        from django_pim.services import upload_picture
        from tests.factories import ProductFactory

        product_with = ProductFactory(shop=shop)
        product_without = ProductFactory(shop=shop)

        buf = io.BytesIO()
        PILImage.new("RGB", (10, 10), color="red").save(buf, format="PNG")
        buf.seek(0)
        img_file = SimpleUploadedFile("media.png", buf.read(), content_type="image/png")
        picture = upload_picture(img_file)
        ProductPicture.objects.create(
            product=product_with, picture=picture, picture_role=PictureRoleEnum.MAIN, position=0
        )

        # has_media=true
        url = f"/api/pim/admin/{shop.idx}/products/?has_media=true"
        response = authenticated_client.get(url)
        assert response.status_code == 200
        skus_with = [p["sku"] for p in response.json()["results"]]
        assert product_with.sku in skus_with
        assert product_without.sku not in skus_with

        # has_media=false
        url = f"/api/pim/admin/{shop.idx}/products/?has_media=false"
        response = authenticated_client.get(url)
        assert response.status_code == 200
        skus_without = [p["sku"] for p in response.json()["results"]]
        assert product_without.sku in skus_without
        assert product_with.sku not in skus_without

    def test_list_products_search_matches_ean(self, authenticated_client, shop):
        """Search matches products by EAN."""
        from tests.factories import ProductFactory, RealProductFactory

        rp = RealProductFactory(sku="EAN-TEST-001", ean="5901234567890")
        ProductFactory(shop=shop, real_product=rp)

        url = f"/api/pim/admin/{shop.idx}/products/?search=5901234"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        skus = [p["sku"] for p in data["results"]]
        assert "EAN-TEST-001" in skus

    def test_list_products_combined_filters(self, authenticated_client, shop):
        """Multiple filters applied together narrow results correctly."""
        from tests.factories import ProductFactory

        # Matches all criteria
        ProductFactory(shop=shop, visibility=4, product_class=1, is_enabled=True)
        # Wrong visibility
        ProductFactory(shop=shop, visibility=1, product_class=1, is_enabled=True)
        # Wrong class
        ProductFactory(shop=shop, visibility=4, product_class=2, is_enabled=True)
        # Disabled
        ProductFactory(shop=shop, visibility=4, product_class=1, is_enabled=False)

        url = f"/api/pim/admin/{shop.idx}/products/?visibility=4&product_class=1&is_enabled=true"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        for p in data["results"]:
            assert p["visibility_int"] == 4
            assert p["product_class"] == 1
            assert p["is_enabled"] is True


# ============================================================================
# Category Endpoints Tests
# ============================================================================


@pytest.mark.django_db
class TestCategoryEndpoints:
    """Test Category admin endpoints."""

    @pytest.fixture
    def category(self, shop, db):
        """Create test category."""
        from tests.factories import ProductCategoryFactory

        return ProductCategoryFactory(shop=shop)

    def test_list_categories(self, authenticated_client, shop, category):
        """Test GET /categories/ returns category list."""
        url = f"/api/pim/admin/{shop.idx}/categories/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "results" in data
        assert len(data["results"]) > 0

        # Check category data structure
        category_data = data["results"][0]
        assert "pk" in category_data
        assert "idx" in category_data
        assert "name" in category_data
        assert "parent_category" in category_data
        assert "is_active" in category_data

    def test_retrieve_category_by_idx(self, authenticated_client, shop, category):
        """Test GET /categories/{idx}/ returns category details."""
        url = f"/api/pim/admin/{shop.idx}/categories/{category.idx}/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["idx"] == category.idx
        assert data["name"] == category.name

    def test_list_categories_with_search(self, authenticated_client, shop, category):
        """Test category search filter."""
        # Test search with idx (which is guaranteed to exist)
        search_term = category.idx
        url = f"/api/pim/admin/{shop.idx}/categories/?search={search_term}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "results" in data

    def test_list_categories_root_only(self, authenticated_client, shop):
        """Test root_only filter."""
        url = f"/api/pim/admin/{shop.idx}/categories/?root_only=true"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # All returned categories should have no parent
        for cat in data["results"]:
            assert cat["parent_category"] is None

    def test_list_categories_with_is_active_filter(self, authenticated_client, shop, category):
        """Test is_active filter."""
        url = f"/api/pim/admin/{shop.idx}/categories/?is_active=true"
        response = authenticated_client.get(url)

        assert response.status_code == 200


# ============================================================================
# Feature Endpoints Tests
# ============================================================================


@pytest.mark.django_db
class TestFeatureEndpoints:
    """Test Feature admin endpoints."""

    @pytest.fixture
    def feature(self, db):
        """Create test feature."""
        from tests.factories import FeatureFactory

        return FeatureFactory()

    def test_list_features(self, authenticated_client, shop, feature):
        """Test GET /features/ returns feature list."""
        url = f"/api/pim/admin/{shop.idx}/features/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "results" in data

        if len(data["results"]) > 0:
            feature_data = data["results"][0]
            assert "pk" in feature_data
            assert "idx" in feature_data
            assert "name" in feature_data
            assert "scope" in feature_data
            assert "scope_name" in feature_data
            assert "feature_type" in feature_data
            assert "feature_type_name" in feature_data
            assert "is_filterable" in feature_data
            assert "is_searchable" in feature_data

    def test_retrieve_feature_by_idx(self, authenticated_client, shop, feature):
        """Test GET /features/{idx}/ returns feature details."""
        url = f"/api/pim/admin/{shop.idx}/features/{feature.idx}/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["idx"] == feature.idx
        assert "feature_type" in data
        assert "feature_type_name" in data

    def test_list_features_with_filters(self, authenticated_client, shop):
        """Test feature filters."""
        url = f"/api/pim/admin/{shop.idx}/features/?is_filterable=true&is_searchable=true"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # All returned features should match filters
        for feat in data["results"]:
            assert feat["is_filterable"] is True
            assert feat["is_searchable"] is True

    def test_list_feature_attributes(self, authenticated_client, shop, feature):
        """Test GET /features/{idx}/attributes/ nested endpoint."""
        url = f"/api/pim/admin/{shop.idx}/features/{feature.idx}/attributes/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "results" in data

    def test_list_features_with_search_by_name(self, authenticated_client, shop, feature):
        """Test feature search by name in name_t9n."""
        # Feature factory creates with name_t9n containing default translations
        url = f"/api/pim/admin/{shop.idx}/features/?search=test"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "results" in data


# ============================================================================
# FeatureSet Endpoints Tests
# ============================================================================


@pytest.mark.django_db
class TestFeatureSetEndpoints:
    """Test FeatureSet admin endpoints."""

    @pytest.fixture
    def feature_set(self, db):
        """Create test feature set."""
        from tests.factories import FeatureSetFactory

        return FeatureSetFactory()

    def test_list_feature_sets(self, authenticated_client, shop, feature_set):
        """Test GET /feature-sets/ returns list."""
        url = f"/api/pim/admin/{shop.idx}/feature-sets/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "results" in data

        if len(data["results"]) > 0:
            fs_data = data["results"][0]
            assert "pk" in fs_data
            assert "idx" in fs_data
            assert "name" in fs_data
            assert "is_default" in fs_data
            assert "feature_count" in fs_data

    def test_retrieve_feature_set_by_idx(self, authenticated_client, shop, feature_set):
        """Test GET /feature-sets/{idx}/ returns details."""
        url = f"/api/pim/admin/{shop.idx}/feature-sets/{feature_set.idx}/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["idx"] == feature_set.idx
        assert "feature_count" in data

    def test_list_features_in_set(self, authenticated_client, shop, feature_set):
        """Test GET /feature-sets/{idx}/features/ nested endpoint."""
        url = f"/api/pim/admin/{shop.idx}/feature-sets/{feature_set.idx}/features/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "results" in data

        # Check nested structure with position
        for item in data["results"]:
            assert "position" in item
            assert "feature" in item

    def test_list_feature_sets_with_search(self, authenticated_client, shop, feature_set):
        """Test feature set search by idx or name."""
        search_term = feature_set.idx[:5]  # Use partial idx
        url = f"/api/pim/admin/{shop.idx}/feature-sets/?search={search_term}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] >= 1


# ============================================================================
# Attribute Endpoints Tests
# ============================================================================


@pytest.mark.django_db
class TestAttributeEndpoints:
    """Test Attribute admin endpoints."""

    @pytest.fixture
    def attribute(self, db):
        """Create test attribute."""
        from tests.factories import AttributeFactory, FeatureFactory

        feature = FeatureFactory()
        return AttributeFactory(feature=feature)

    def test_list_attributes(self, authenticated_client, attribute):
        """Test GET /attributes/ returns list."""
        url = "/api/pim/admin/attributes/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "results" in data

        if len(data["results"]) > 0:
            attr_data = data["results"][0]
            assert "pk" in attr_data
            assert "feature_idx" in attr_data
            assert "idx" in attr_data
            assert "name" in attr_data
            assert "display_order" in attr_data

    def test_retrieve_attribute_by_composite_key(self, authenticated_client, attribute):
        """Test GET /attributes/{feature_idx}/{idx}/ with composite key."""
        url = f"/api/pim/admin/attributes/{attribute.feature.idx}/{attribute.idx}/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["feature_idx"] == attribute.feature.idx
        assert data["idx"] == attribute.idx

    def test_list_attributes_with_feature_filter(self, authenticated_client, attribute):
        """Test attribute filtering by feature."""
        url = f"/api/pim/admin/attributes/?feature_idx={attribute.feature.idx}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # All returned attributes should belong to the feature
        for attr in data["results"]:
            assert attr["feature_idx"] == attribute.feature.idx


# ============================================================================
# AttributesGroup Endpoints Tests
# ============================================================================


@pytest.mark.django_db
class TestAttributesGroupEndpoints:
    """Test AttributesGroup admin endpoints."""

    @pytest.fixture
    def attributes_group(self, db):
        """Create test attributes group."""
        return AttributesGroup.objects.create(idx="test-group")

    def test_list_attributes_groups(self, authenticated_client, shop, attributes_group):
        """Test GET /attributes-groups/ returns list."""
        url = f"/api/pim/admin/{shop.idx}/attributes-groups/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "results" in data

        if len(data["results"]) > 0:
            group_data = data["results"][0]
            assert "pk" in group_data
            assert "idx" in group_data
            assert "name" in group_data
            assert "attribute_count" in group_data

    def test_retrieve_attributes_group_by_idx(self, authenticated_client, shop, attributes_group):
        """Test GET /attributes-groups/{idx}/ returns details."""
        url = f"/api/pim/admin/{shop.idx}/attributes-groups/{attributes_group.idx}/"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["idx"] == attributes_group.idx

    def test_list_attributes_groups_with_search(self, authenticated_client, shop, attributes_group):
        """Test attributes group search by idx."""
        search_term = attributes_group.idx[:4]  # Use partial idx
        url = f"/api/pim/admin/{shop.idx}/attributes-groups/?search={search_term}"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] >= 1


# ============================================================================
# Pagination Tests
# ============================================================================


@pytest.mark.django_db
class TestPagination:
    """Test pagination across all endpoints."""

    def test_pagination_page_parameter(self, authenticated_client, shop):
        """Test page parameter works."""
        url = f"/api/pim/admin/{shop.idx}/products/?page=1&page_size=5"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert len(data["results"]) <= 5

    def test_pagination_links(self, authenticated_client, shop):
        """Test next/previous pagination links."""
        # Create enough products for multiple pages
        from tests.factories import ProductFactory

        # Create products - factory handles uniqueness
        for i in range(25):
            ProductFactory(shop=shop)

        url = f"/api/pim/admin/{shop.idx}/products/?page=1&page_size=10"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["count"] >= 25
        if data["count"] > 10:
            assert data["next"] is not None  # Should have next page
        assert data["previous"] is None  # First page has no previous

    def test_pagination_max_page_size(self, authenticated_client, shop):
        """Test max page size limit (100)."""
        url = f"/api/pim/admin/{shop.idx}/products/?page_size=200"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Should be capped at 100
        assert len(data["results"]) <= 100


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.django_db
class TestErrorHandling:
    """Test error responses."""

    def test_404_product_not_found(self, authenticated_client, shop):
        """Test 404 when product doesn't exist."""
        url = f"/api/pim/admin/{shop.idx}/products/NONEXISTENT-SKU/"
        response = authenticated_client.get(url)

        assert response.status_code == 404
        assert "not found" in str(response.data).lower()

    def test_404_category_not_found(self, authenticated_client, shop):
        """Test 404 when category doesn't exist."""
        url = f"/api/pim/admin/{shop.idx}/categories/nonexistent-idx/"
        response = authenticated_client.get(url)

        assert response.status_code == 404

    def test_404_feature_not_found(self, authenticated_client, shop):
        """Test 404 when feature doesn't exist."""
        url = f"/api/pim/admin/{shop.idx}/features/nonexistent-idx/"
        response = authenticated_client.get(url)

        assert response.status_code == 404

    def test_404_attribute_not_found(self, authenticated_client):
        """Test 404 when attribute doesn't exist with composite key."""
        url = "/api/pim/admin/attributes/nonexistent-feature/nonexistent-attr/"
        response = authenticated_client.get(url)

        assert response.status_code == 404


# ============================================================================
# Attribute Filter Tests
# ============================================================================


@pytest.mark.django_db
class TestAttributeFiltering:
    """Test filtering products by attribute values via attr_* query params."""

    def test_list_products_with_attribute_filter(self, authenticated_client, shop):
        """Products can be filtered by a single attr_{feature_idx}={attribute_idx} param."""
        from django_pim.models import FeatureInFeatureSet, FeatureTypeEnum
        from tests.factories import (
            AttributeFactory,
            FeatureFactory,
            FeatureSetFactory,
            ProductAttributeFactory,
            ProductFactory,
            RealProductFactory,
        )

        feature_set = FeatureSetFactory()
        color_feature = FeatureFactory(idx="color", feature_type=FeatureTypeEnum.SELECT, is_filterable=True)
        # ProductAttribute requires its feature to belong to the product's feature set
        FeatureInFeatureSet.objects.create(feature_set=feature_set, feature=color_feature)
        red_attr = AttributeFactory(feature=color_feature, idx="red")
        blue_attr = AttributeFactory(feature=color_feature, idx="blue")

        rp1 = RealProductFactory(sku="RED-PROD")
        rp2 = RealProductFactory(sku="BLUE-PROD")
        p1 = ProductFactory(real_product=rp1, shop=shop, feature_set=feature_set)
        p2 = ProductFactory(real_product=rp2, shop=shop, feature_set=feature_set)
        ProductAttributeFactory(product=p1, feature=color_feature, attribute=red_attr)
        ProductAttributeFactory(product=p2, feature=color_feature, attribute=blue_attr)

        url = f"/api/pim/admin/{shop.idx}/products/?attr_color=red"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        skus = [r["sku"] for r in data["results"]]
        assert "RED-PROD" in skus
        assert "BLUE-PROD" not in skus

    def test_list_products_with_multiple_attribute_filters(self, authenticated_client, shop):
        """Multiple attr_* params are ANDed — product must match all."""
        from django_pim.models import FeatureInFeatureSet, FeatureTypeEnum
        from tests.factories import (
            AttributeFactory,
            FeatureFactory,
            FeatureSetFactory,
            ProductAttributeFactory,
            ProductFactory,
            RealProductFactory,
        )

        feature_set = FeatureSetFactory()
        color = FeatureFactory(idx="af-color", feature_type=FeatureTypeEnum.SELECT, is_filterable=True)
        material = FeatureFactory(idx="af-material", feature_type=FeatureTypeEnum.SELECT, is_filterable=True)
        # ProductAttribute requires its feature to belong to the product's feature set
        FeatureInFeatureSet.objects.create(feature_set=feature_set, feature=color)
        FeatureInFeatureSet.objects.create(feature_set=feature_set, feature=material)
        red = AttributeFactory(feature=color, idx="af-red")
        wood = AttributeFactory(feature=material, idx="af-wood")
        metal = AttributeFactory(feature=material, idx="af-metal")

        rp1 = RealProductFactory(sku="RED-WOOD")
        rp2 = RealProductFactory(sku="RED-METAL")
        p1 = ProductFactory(real_product=rp1, shop=shop, feature_set=feature_set)
        p2 = ProductFactory(real_product=rp2, shop=shop, feature_set=feature_set)
        ProductAttributeFactory(product=p1, feature=color, attribute=red)
        ProductAttributeFactory(product=p1, feature=material, attribute=wood)
        ProductAttributeFactory(product=p2, feature=color, attribute=red)
        ProductAttributeFactory(product=p2, feature=material, attribute=metal)

        url = f"/api/pim/admin/{shop.idx}/products/?attr_af-color=af-red&attr_af-material=af-wood"
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        skus = [r["sku"] for r in data["results"]]
        assert "RED-WOOD" in skus
        assert "RED-METAL" not in skus
