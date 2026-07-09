# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
CRUD tests for PIM Admin API - Product Pictures and Picture Upload.

Covers:
- JWT authentication and authorization for picture endpoints
- Global picture upload with SHA1 deduplication
- Product picture list, retrieve, link, update, unlink lifecycle
- Multipart upload + link in one step
- Picture persistence after unlinking (ProductPicture deleted, Picture remains)

URL prefix: /api/pim/admin/
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from django_pim.models import Picture


@pytest.fixture
def shop(db):
    from tests.factories import ChannelFactory

    return ChannelFactory(idx="test-pics-channel", name="Test Pics Channel")


@pytest.fixture
def product(shop):
    from tests.factories import FeatureSetFactory, ProductFactory, RealProductFactory

    fs = FeatureSetFactory()
    rp = RealProductFactory(sku="PIC-PROD-1")
    return ProductFactory(shop=shop, feature_set=fs, real_product=rp)


def create_test_image(name: str = "test.jpg", size: tuple = (100, 100), color: str = "red") -> SimpleUploadedFile:
    """Create an in-memory JPEG/PNG for upload tests."""
    fmt = "PNG" if name.endswith(".png") else "JPEG"
    ct = "image/png" if fmt == "PNG" else "image/jpeg"
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format=fmt)
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type=ct)


# ============================================================================
# TestPictureUploadAuth
# ============================================================================


@pytest.mark.django_db
class TestPictureUploadAuth:
    """Authentication checks for the global picture upload endpoint."""

    def test_unauthenticated_post_returns_401(self, api_client):
        image = create_test_image()
        response = api_client.post("/api/pim/admin/pictures/upload/", {"image": image}, format="multipart")
        assert response.status_code == 401

    def test_admin_upload_returns_201(self, authenticated_client):
        image = create_test_image()
        response = authenticated_client.post("/api/pim/admin/pictures/upload/", {"image": image}, format="multipart")
        assert response.status_code == 201


# ============================================================================
# TestPictureUpload
# ============================================================================


@pytest.mark.django_db
class TestPictureUpload:
    """Functional tests for global picture upload."""

    def test_upload_returns_picture_response_fields(self, authenticated_client):
        image = create_test_image(name="chair.jpg")
        response = authenticated_client.post("/api/pim/admin/pictures/upload/", {"image": image}, format="multipart")

        assert response.status_code == 201
        data = response.json()
        assert "pk" in data
        assert "sha1" in data
        assert "width" in data
        assert "height" in data
        assert "original_file_name" in data
        assert "image_url" in data
        assert data["original_file_name"] == "chair.jpg"

    def test_upload_same_image_twice_returns_same_pk(self, authenticated_client):
        """SHA1 deduplication: identical content returns the existing Picture."""
        image_first = create_test_image(name="dup.jpg", color="blue")
        image_second = create_test_image(name="dup-copy.jpg", color="blue")

        response_first = authenticated_client.post(
            "/api/pim/admin/pictures/upload/", {"image": image_first}, format="multipart"
        )
        response_second = authenticated_client.post(
            "/api/pim/admin/pictures/upload/", {"image": image_second}, format="multipart"
        )

        assert response_first.status_code == 201
        assert response_second.status_code == 201
        assert response_first.json()["pk"] == response_second.json()["pk"]

    def test_upload_without_image_file_returns_400(self, authenticated_client):
        response = authenticated_client.post("/api/pim/admin/pictures/upload/", {}, format="multipart")
        assert response.status_code == 400


# ============================================================================
# TestProductPictureAuth
# ============================================================================


@pytest.mark.django_db
class TestProductPictureAuth:
    """Authentication checks for product picture endpoints."""

    def test_unauthenticated_list_returns_401(self, api_client, shop, product):
        sku = product.real_product.sku
        response = api_client.get(f"/api/pim/admin/{shop.idx}/products/{sku}/pictures/")
        assert response.status_code == 401

    def test_admin_list_returns_200(self, authenticated_client, shop, product):
        sku = product.real_product.sku
        response = authenticated_client.get(f"/api/pim/admin/{shop.idx}/products/{sku}/pictures/")
        assert response.status_code == 200


# ============================================================================
# TestProductPictureCRUD
# ============================================================================


@pytest.mark.django_db
class TestProductPictureCRUD:
    """Full CRUD lifecycle for product picture assignments."""

    def _list_url(self, shop_idx: str, sku: str) -> str:
        return f"/api/pim/admin/{shop_idx}/products/{sku}/pictures/"

    def _detail_url(self, shop_idx: str, sku: str, pk: int) -> str:
        return f"/api/pim/admin/{shop_idx}/products/{sku}/pictures/{pk}/"

    def _upload_url(self) -> str:
        return "/api/pim/admin/pictures/upload/"

    def test_list_empty_for_product_with_no_pictures(self, authenticated_client, shop, product):
        sku = product.real_product.sku
        response = authenticated_client.get(self._list_url(shop.idx, sku))

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_link_existing_picture_returns_201(self, authenticated_client, shop, product):
        """Link an already-uploaded picture via JSON body with picture_pk."""
        image = create_test_image(name="link-test.jpg", color="green")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        assert upload_response.status_code == 201
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        response = authenticated_client.post(self._list_url(shop.idx, sku), {"picture_pk": picture_pk}, format="json")

        assert response.status_code == 201
        data = response.json()
        assert data["picture"]["pk"] == picture_pk

    def test_link_with_role_main(self, authenticated_client, shop, product):
        """Link with explicit role='main' stores the correct role."""
        image = create_test_image(name="main-pic.jpg", color="yellow")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        response = authenticated_client.post(
            self._list_url(shop.idx, sku), {"picture_pk": picture_pk, "picture_role": "main"}, format="json"
        )

        assert response.status_code == 201
        assert response.json()["picture_role"] == "main"

    def test_multipart_upload_and_link_returns_201(self, authenticated_client, shop, product):
        """POST with an image file uploads and links in one request."""
        image = create_test_image(name="multipart-upload.jpg", color="purple")
        sku = product.real_product.sku

        response = authenticated_client.post(
            self._list_url(shop.idx, sku),
            {"image": image, "picture_role": "general", "position": "0"},
            format="multipart",
        )

        assert response.status_code == 201
        data = response.json()
        assert "pk" in data
        assert "picture" in data
        assert data["picture_role"] == "general"

    def test_retrieve_product_picture_returns_200(self, authenticated_client, shop, product):
        image = create_test_image(name="retrieve-test.jpg", color="cyan")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        create_response = authenticated_client.post(
            self._list_url(shop.idx, sku), {"picture_pk": picture_pk}, format="json"
        )
        pp_pk = create_response.json()["pk"]

        response = authenticated_client.get(self._detail_url(shop.idx, sku, pp_pk))

        assert response.status_code == 200
        data = response.json()
        assert data["pk"] == pp_pk
        assert data["picture"]["pk"] == picture_pk

    def test_update_picture_assignment_returns_200(self, authenticated_client, shop, product):
        """PATCH changes role and position on the ProductPicture."""
        image = create_test_image(name="update-test.jpg", color="orange")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        create_response = authenticated_client.post(
            self._list_url(shop.idx, sku), {"picture_pk": picture_pk, "picture_role": "general"}, format="json"
        )
        pp_pk = create_response.json()["pk"]

        response = authenticated_client.patch(self._detail_url(shop.idx, sku, pp_pk), {"position": 5}, format="json")

        assert response.status_code == 200
        assert response.json()["position"] == 5

    def test_unlink_picture_returns_200(self, authenticated_client, shop, product):
        """DELETE removes ProductPicture assignment."""
        image = create_test_image(name="unlink-test.jpg", color="pink")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        create_response = authenticated_client.post(
            self._list_url(shop.idx, sku), {"picture_pk": picture_pk}, format="json"
        )
        pp_pk = create_response.json()["pk"]

        response = authenticated_client.delete(self._detail_url(shop.idx, sku, pp_pk))

        assert response.status_code == 200

    def test_picture_still_exists_after_unlink(self, authenticated_client, shop, product):
        """Unlinking removes ProductPicture but leaves the Picture record intact."""
        image = create_test_image(name="persist-test.jpg", color="teal")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        create_response = authenticated_client.post(
            self._list_url(shop.idx, sku), {"picture_pk": picture_pk}, format="json"
        )
        pp_pk = create_response.json()["pk"]

        authenticated_client.delete(self._detail_url(shop.idx, sku, pp_pk))

        assert Picture.objects.filter(pk=picture_pk).exists()

    def test_invalid_picture_pk_returns_404(self, authenticated_client, shop, product):
        sku = product.real_product.sku
        response = authenticated_client.post(self._list_url(shop.idx, sku), {"picture_pk": 999999}, format="json")
        assert response.status_code == 404

    def test_list_returns_paginated_structure(self, authenticated_client, shop, product):
        """List response includes count, next, previous, results."""
        response = authenticated_client.get(self._list_url(shop.idx, product.real_product.sku))

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

    def test_list_includes_linked_picture(self, authenticated_client, shop, product):
        """After linking, the picture appears in the list."""
        image = create_test_image(name="list-verify.jpg", color="navy")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        authenticated_client.post(self._list_url(shop.idx, sku), {"picture_pk": picture_pk}, format="json")

        list_response = authenticated_client.get(self._list_url(shop.idx, sku))
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1

    def test_retrieve_after_unlink_returns_404(self, authenticated_client, shop, product):
        """Retrieving an unlinked ProductPicture pk returns 404."""
        image = create_test_image(name="404-test.jpg", color="maroon")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku
        create_response = authenticated_client.post(
            self._list_url(shop.idx, sku), {"picture_pk": picture_pk}, format="json"
        )
        pp_pk = create_response.json()["pk"]

        authenticated_client.delete(self._detail_url(shop.idx, sku, pp_pk))

        response = authenticated_client.get(self._detail_url(shop.idx, sku, pp_pk))
        assert response.status_code == 404

    def test_full_lifecycle(self, authenticated_client, shop, product):
        """UPLOAD -> LINK -> GET -> UPDATE -> UNLINK -> GET 404."""
        # UPLOAD
        image = create_test_image(name="lifecycle.jpg", color="lime")
        upload_response = authenticated_client.post(self._upload_url(), {"image": image}, format="multipart")
        assert upload_response.status_code == 201
        picture_pk = upload_response.json()["pk"]

        sku = product.real_product.sku

        # LINK
        link_response = authenticated_client.post(
            self._list_url(shop.idx, sku),
            {"picture_pk": picture_pk, "picture_role": "general", "position": 1},
            format="json",
        )
        assert link_response.status_code == 201
        pp_pk = link_response.json()["pk"]

        # GET
        get_response = authenticated_client.get(self._detail_url(shop.idx, sku, pp_pk))
        assert get_response.status_code == 200
        assert get_response.json()["position"] == 1

        # UPDATE
        patch_response = authenticated_client.patch(
            self._detail_url(shop.idx, sku, pp_pk), {"position": 10}, format="json"
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["position"] == 10

        # UNLINK
        delete_response = authenticated_client.delete(self._detail_url(shop.idx, sku, pp_pk))
        assert delete_response.status_code == 200

        # GET 404
        not_found_response = authenticated_client.get(self._detail_url(shop.idx, sku, pp_pk))
        assert not_found_response.status_code == 404

        # Picture still exists
        assert Picture.objects.filter(pk=picture_pk).exists()
