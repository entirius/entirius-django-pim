# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for Product Videos Admin API.

Covers:
- JWT authentication and IsAdminUser enforcement
- Full CRUD lifecycle for product video assignments
- Auto-detection of video source (YouTube/Vimeo/Unknown)
- Response structure validation against ProductVideoResponse schema
- Invalid role rejection (400)

URL prefix: /api/pim/admin/
"""

import pytest


@pytest.fixture
def shop(db):
    from tests.factories import ChannelFactory

    return ChannelFactory(idx="test-videos-channel", name="Test Videos Channel")


@pytest.fixture
def product(shop):
    from tests.factories import FeatureSetFactory, ProductFactory, RealProductFactory

    fs = FeatureSetFactory()
    rp = RealProductFactory(sku="VIDEO-PROD-1")
    return ProductFactory(shop=shop, feature_set=fs, real_product=rp)


# ============================================================================
# Authentication Tests
# ============================================================================


@pytest.mark.django_db
class TestProductVideoAuth:
    """Verify JWT + IsAdminUser enforcement on video endpoints."""

    def test_unauthenticated_request_returns_401(self, api_client, shop, product):
        sku = product.real_product.sku
        url = f"/api/pim/admin/{shop.idx}/products/{sku}/videos/"
        response = api_client.get(url)

        assert response.status_code == 401

    def test_admin_user_returns_200(self, api_client, admin_token, shop, product):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        sku = product.real_product.sku
        url = f"/api/pim/admin/{shop.idx}/products/{sku}/videos/"
        response = api_client.get(url)

        assert response.status_code == 200


# ============================================================================
# CRUD Tests
# ============================================================================


@pytest.mark.django_db
class TestProductVideoCRUD:
    """Full CRUD lifecycle for product video assignments."""

    YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    VIMEO_URL = "https://vimeo.com/123456789"
    UNKNOWN_URL = "https://example.com/video.mp4"

    def _list_url(self, shop, product):
        return f"/api/pim/admin/{shop.idx}/products/{product.real_product.sku}/videos/"

    def _detail_url(self, shop, product, pk):
        return f"/api/pim/admin/{shop.idx}/products/{product.real_product.sku}/videos/{pk}/"

    def test_list_returns_empty_for_product_with_no_videos(self, authenticated_client, shop, product):
        response = authenticated_client.get(self._list_url(shop, product))

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []
        assert "next" in data
        assert "previous" in data

    def test_create_youtube_url_returns_201_with_source_youtube(self, authenticated_client, shop, product):
        payload = {"video_url": self.YOUTUBE_URL, "title": "YouTube Test Video"}
        response = authenticated_client.post(self._list_url(shop, product), payload, format="json")

        assert response.status_code == 201
        data = response.json()
        assert data["video"]["source"] == "youtube"
        assert data["video"]["video_url"] == self.YOUTUBE_URL

    def test_create_vimeo_url_returns_201_with_source_vimeo(self, authenticated_client, shop, product):
        payload = {"video_url": self.VIMEO_URL, "title": "Vimeo Test Video"}
        response = authenticated_client.post(self._list_url(shop, product), payload, format="json")

        assert response.status_code == 201
        data = response.json()
        assert data["video"]["source"] == "vimeo"

    def test_create_unknown_url_returns_201_with_source_unknown(self, authenticated_client, shop, product):
        payload = {"video_url": self.UNKNOWN_URL}
        response = authenticated_client.post(self._list_url(shop, product), payload, format="json")

        assert response.status_code == 201
        data = response.json()
        assert data["video"]["source"] == "unknown"

    def test_create_response_has_expected_fields(self, authenticated_client, shop, product):
        payload = {"video_url": self.YOUTUBE_URL, "title": "Field Check Video"}
        response = authenticated_client.post(self._list_url(shop, product), payload, format="json")

        assert response.status_code == 201
        data = response.json()

        # ProductVideoResponse top-level fields
        assert "pk" in data
        assert "video" in data
        assert "video_role" in data
        assert "video_role_name" in data
        assert "language_iso2" in data
        assert "position" in data

        # Nested VideoResponse fields
        video = data["video"]
        assert "pk" in video
        assert "title" in video
        assert "is_external" in video
        assert "source" in video
        assert "source_name" in video
        assert "video_url" in video

    def test_create_with_role_main(self, authenticated_client, shop, product):
        payload = {"video_url": self.YOUTUBE_URL, "title": "Main Role Video", "video_role": "main"}
        response = authenticated_client.post(self._list_url(shop, product), payload, format="json")

        assert response.status_code == 201
        data = response.json()
        assert data["video_role"] == "main"

    def test_retrieve_by_pk_returns_200(self, authenticated_client, shop, product):
        # Create first
        create_response = authenticated_client.post(
            self._list_url(shop, product), {"video_url": self.YOUTUBE_URL}, format="json"
        )
        assert create_response.status_code == 201
        pk = create_response.json()["pk"]

        response = authenticated_client.get(self._detail_url(shop, product, pk))

        assert response.status_code == 200
        data = response.json()
        assert data["pk"] == pk

    def test_update_title_returns_200(self, authenticated_client, shop, product):
        create_response = authenticated_client.post(
            self._list_url(shop, product), {"video_url": self.YOUTUBE_URL, "title": "Original Title"}, format="json"
        )
        pk = create_response.json()["pk"]

        response = authenticated_client.patch(
            self._detail_url(shop, product, pk), {"title": "Updated Title"}, format="json"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["video"]["title"] == "Updated Title"

    def test_update_role_from_unknown_to_main_returns_200(self, authenticated_client, shop, product):
        create_response = authenticated_client.post(
            self._list_url(shop, product), {"video_url": self.VIMEO_URL, "video_role": "unknown"}, format="json"
        )
        pk = create_response.json()["pk"]

        response = authenticated_client.patch(
            self._detail_url(shop, product, pk), {"video_role": "main"}, format="json"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["video_role"] == "main"

    def test_delete_returns_200_with_deleted_key(self, authenticated_client, shop, product):
        create_response = authenticated_client.post(
            self._list_url(shop, product), {"video_url": self.YOUTUBE_URL}, format="json"
        )
        pk = create_response.json()["pk"]

        response = authenticated_client.delete(self._detail_url(shop, product, pk))

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data

    def test_full_lifecycle_create_get_update_delete(self, authenticated_client, shop, product):
        list_url = self._list_url(shop, product)

        # CREATE
        create_response = authenticated_client.post(
            list_url, {"video_url": self.YOUTUBE_URL, "title": "Lifecycle Video"}, format="json"
        )
        assert create_response.status_code == 201
        pk = create_response.json()["pk"]

        # GET
        get_response = authenticated_client.get(self._detail_url(shop, product, pk))
        assert get_response.status_code == 200
        assert get_response.json()["pk"] == pk

        # UPDATE
        patch_response = authenticated_client.patch(
            self._detail_url(shop, product, pk), {"title": "Updated Lifecycle Video", "position": 5}, format="json"
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["position"] == 5

        # DELETE
        delete_response = authenticated_client.delete(self._detail_url(shop, product, pk))
        assert delete_response.status_code == 200

        # GET after DELETE returns 404
        get_after_delete = authenticated_client.get(self._detail_url(shop, product, pk))
        assert get_after_delete.status_code == 404

    def test_invalid_role_returns_400(self, authenticated_client, shop, product):
        payload = {"video_url": self.YOUTUBE_URL, "video_role": "nonexistent-role"}
        response = authenticated_client.post(self._list_url(shop, product), payload, format="json")

        assert response.status_code == 400
