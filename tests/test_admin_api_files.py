# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for PIM Admin API — Product Files, File Upload, and Files Categories.

Covers:
- FilesCategory CRUD lifecycle
- File upload with SHA1 deduplication
- ProductFile link/unlink lifecycle

URL prefix: /api/pim/admin/
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.fixture
def shop(db):
    from tests.factories import ChannelFactory

    return ChannelFactory(idx="test-files-channel", name="Test Files Channel")


@pytest.fixture
def product(shop):
    from tests.factories import FeatureSetFactory, ProductFactory, RealProductFactory

    fs = FeatureSetFactory()
    rp = RealProductFactory(sku="FILE-PROD-1")
    return ProductFactory(shop=shop, feature_set=fs, real_product=rp)


def create_test_file(
    name: str = "test.pdf", content: bytes = b"fake pdf content", content_type: str = "application/pdf"
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)


# ============================================================================
# FilesCategory Auth
# ============================================================================


@pytest.mark.django_db
class TestFilesCategoryAuth:
    """Files categories require admin authentication."""

    def test_unauthenticated_get_files_categories_returns_401(self, api_client):
        response = api_client.get("/api/pim/admin/files-categories/")
        assert response.status_code == 401

    def test_admin_get_files_categories_returns_200(self, authenticated_client):
        response = authenticated_client.get("/api/pim/admin/files-categories/")
        assert response.status_code == 200


# ============================================================================
# FilesCategory CRUD
# ============================================================================


@pytest.mark.django_db
class TestFilesCategoryCRUD:
    """Full CRUD lifecycle for file categories."""

    def test_list_returns_paginated_results(self, authenticated_client):
        from tests.factories import FilesCategoryFactory

        FilesCategoryFactory(code="manual-list-1", name_t9n={"en": "Manual 1"})
        FilesCategoryFactory(code="manual-list-2", name_t9n={"en": "Manual 2"})

        response = authenticated_client.get("/api/pim/admin/files-categories/")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "results" in data
        assert data["count"] >= 2

    def test_create_returns_201_with_code_name_t9n_name(self, authenticated_client):
        response = authenticated_client.post(
            "/api/pim/admin/files-categories/",
            {"code": "new-manual", "name_t9n": {"en": "Manual", "pl": "Instrukcja"}},
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "new-manual"
        assert data["name_t9n"] == {"en": "Manual", "pl": "Instrukcja"}
        assert "name" in data

    def test_create_duplicate_code_returns_400(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/files-categories/", {"code": "dup-cat", "name_t9n": {"en": "Dup"}}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/files-categories/", {"code": "dup-cat", "name_t9n": {"en": "Dup Again"}}, format="json"
        )

        assert response.status_code == 400

    def test_retrieve_by_code_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/files-categories/",
            {"code": "retrieve-cat", "name_t9n": {"en": "Retrieve Me"}},
            format="json",
        )

        response = authenticated_client.get("/api/pim/admin/files-categories/retrieve-cat/")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "retrieve-cat"

    def test_update_name_t9n_returns_200(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/files-categories/", {"code": "update-cat", "name_t9n": {"en": "Original"}}, format="json"
        )

        response = authenticated_client.patch(
            "/api/pim/admin/files-categories/update-cat/",
            {"name_t9n": {"en": "Updated", "pl": "Zaktualizowane"}},
            format="json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name_t9n"]["en"] == "Updated"

    def test_delete_returns_200_with_deleted_counts(self, authenticated_client):
        authenticated_client.post(
            "/api/pim/admin/files-categories/", {"code": "delete-cat", "name_t9n": {"en": "Delete Me"}}, format="json"
        )

        response = authenticated_client.delete("/api/pim/admin/files-categories/delete-cat/")

        assert response.status_code == 200
        assert "deleted" in response.json()

    def test_full_lifecycle(self, authenticated_client):
        # Create
        r = authenticated_client.post(
            "/api/pim/admin/files-categories/",
            {"code": "lifecycle-cat", "name_t9n": {"en": "Lifecycle"}},
            format="json",
        )
        assert r.status_code == 201

        # Retrieve
        r = authenticated_client.get("/api/pim/admin/files-categories/lifecycle-cat/")
        assert r.status_code == 200
        assert r.json()["code"] == "lifecycle-cat"

        # Update
        r = authenticated_client.patch(
            "/api/pim/admin/files-categories/lifecycle-cat/", {"name_t9n": {"en": "Updated Lifecycle"}}, format="json"
        )
        assert r.status_code == 200
        assert r.json()["name_t9n"]["en"] == "Updated Lifecycle"

        # Delete
        r = authenticated_client.delete("/api/pim/admin/files-categories/lifecycle-cat/")
        assert r.status_code == 200

        # Verify gone
        r = authenticated_client.get("/api/pim/admin/files-categories/lifecycle-cat/")
        assert r.status_code == 404


# ============================================================================
# File Upload
# ============================================================================


@pytest.mark.django_db
class TestFileUpload:
    """File upload endpoint with SHA1 deduplication."""

    def test_upload_returns_201_with_file_response_fields(self, authenticated_client):
        file_obj = create_test_file(name="upload-test.pdf", content=b"unique pdf content for upload test")

        response = authenticated_client.post("/api/pim/admin/files/upload/", {"file": file_obj}, format="multipart")

        assert response.status_code == 201
        data = response.json()
        assert "pk" in data
        assert "sha1" in data
        assert "file_type" in data
        assert "original_file_name" in data
        assert "file_url" in data

    def test_upload_same_file_twice_returns_same_pk(self, authenticated_client):
        content = b"deduplicated content shared across two uploads"

        r1 = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(name="dedup1.pdf", content=content)},
            format="multipart",
        )
        r2 = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(name="dedup2.pdf", content=content)},
            format="multipart",
        )

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["pk"] == r2.json()["pk"]

    def test_upload_without_file_field_returns_400(self, authenticated_client):
        response = authenticated_client.post("/api/pim/admin/files/upload/", {}, format="multipart")

        assert response.status_code == 400


# ============================================================================
# ProductFile CRUD
# ============================================================================


@pytest.mark.django_db
class TestProductFileCRUD:
    """Link/unlink lifecycle for product file attachments."""

    def test_list_returns_empty_for_product_with_no_files(self, authenticated_client, product):
        response = authenticated_client.get("/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_link_existing_file_returns_201(self, authenticated_client, product):
        upload_resp = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(content=b"link test file content abc")},
            format="multipart",
        )
        assert upload_resp.status_code == 201
        file_pk = upload_resp.json()["pk"]

        response = authenticated_client.post(
            "/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/", {"file_pk": file_pk}, format="json"
        )

        assert response.status_code == 201
        data = response.json()
        assert "pk" in data
        assert data["file"]["pk"] == file_pk

    def test_link_duplicate_file_returns_400(self, authenticated_client, product):
        upload_resp = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(content=b"duplicate link test content xyz")},
            format="multipart",
        )
        assert upload_resp.status_code == 201
        file_pk = upload_resp.json()["pk"]

        authenticated_client.post(
            "/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/", {"file_pk": file_pk}, format="json"
        )

        response = authenticated_client.post(
            "/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/", {"file_pk": file_pk}, format="json"
        )

        assert response.status_code == 400

    def test_unlink_file_returns_200(self, authenticated_client, product):
        upload_resp = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(content=b"unlink test file content 123")},
            format="multipart",
        )
        assert upload_resp.status_code == 201
        file_pk = upload_resp.json()["pk"]

        link_resp = authenticated_client.post(
            "/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/", {"file_pk": file_pk}, format="json"
        )
        assert link_resp.status_code == 201
        product_file_pk = link_resp.json()["pk"]

        response = authenticated_client.delete(
            f"/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/{product_file_pk}/"
        )

        assert response.status_code == 200

    def test_full_lifecycle_upload_link_list_unlink_list(self, authenticated_client, product):
        # Upload
        upload_resp = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(content=b"lifecycle file content qwerty")},
            format="multipart",
        )
        assert upload_resp.status_code == 201
        file_pk = upload_resp.json()["pk"]

        # Link
        link_resp = authenticated_client.post(
            "/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/", {"file_pk": file_pk}, format="json"
        )
        assert link_resp.status_code == 201
        product_file_pk = link_resp.json()["pk"]

        # List — expect 1 result
        list_resp = authenticated_client.get("/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/")
        assert list_resp.status_code == 200
        assert list_resp.json()["count"] == 1

        # Unlink
        unlink_resp = authenticated_client.delete(
            f"/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/{product_file_pk}/"
        )
        assert unlink_resp.status_code == 200

        # List — expect 0 results
        list_resp = authenticated_client.get("/api/pim/admin/test-files-channel/products/FILE-PROD-1/files/")
        assert list_resp.status_code == 200
        assert list_resp.json()["count"] == 0


# ============================================================================
# File Type Auto-Detection
# ============================================================================


@pytest.mark.django_db
class TestFileTypeAutoDetection:
    """Upload auto-detects file_type from extension when not provided."""

    def test_upload_pdf_auto_detects_type(self, authenticated_client):
        file_obj = create_test_file(
            name="report.pdf", content=b"auto detect pdf content 001", content_type="application/octet-stream"
        )

        response = authenticated_client.post("/api/pim/admin/files/upload/", {"file": file_obj}, format="multipart")

        assert response.status_code == 201
        assert response.json()["file_type"] == 2  # PDF

    def test_upload_image_auto_detects_type(self, authenticated_client):
        file_obj = create_test_file(
            name="photo.jpg", content=b"auto detect jpg content 002", content_type="application/octet-stream"
        )

        response = authenticated_client.post("/api/pim/admin/files/upload/", {"file": file_obj}, format="multipart")

        assert response.status_code == 201
        assert response.json()["file_type"] == 1  # PICTURE

    def test_upload_unknown_defaults_to_undefined(self, authenticated_client):
        file_obj = create_test_file(
            name="data.xyz", content=b"auto detect unknown content 003", content_type="application/octet-stream"
        )

        response = authenticated_client.post("/api/pim/admin/files/upload/", {"file": file_obj}, format="multipart")

        assert response.status_code == 201
        assert response.json()["file_type"] == 0  # UNDEFINED

    def test_explicit_file_type_overrides_detection(self, authenticated_client):
        file_obj = create_test_file(
            name="photo.jpg", content=b"explicit override content 004", content_type="application/octet-stream"
        )

        response = authenticated_client.post(
            "/api/pim/admin/files/upload/", {"file": file_obj, "file_type": "pdf"}, format="multipart"
        )

        assert response.status_code == 201
        assert response.json()["file_type"] == 2  # PDF (explicit overrides .jpg)


# ============================================================================
# File Update (PATCH)
# ============================================================================


@pytest.mark.django_db
class TestFileUpdate:
    """PATCH endpoint for updating file metadata."""

    def test_patch_file_label_t9n(self, authenticated_client):
        upload_resp = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(content=b"patch label t9n content 001")},
            format="multipart",
        )
        assert upload_resp.status_code == 201
        file_pk = upload_resp.json()["pk"]

        response = authenticated_client.patch(
            f"/api/pim/admin/files/{file_pk}/",
            {"file_label_t9n": {"en": "User Guide", "pl": "Instrukcja"}},
            format="json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_label_t9n"] == {"en": "User Guide", "pl": "Instrukcja"}
        assert data["file_label"] == "User Guide"

    def test_patch_file_category(self, authenticated_client):
        # Create category
        authenticated_client.post(
            "/api/pim/admin/files-categories/",
            {"code": "patch-cat", "name_t9n": {"en": "Patch Category"}},
            format="json",
        )

        # Upload file
        upload_resp = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(content=b"patch category content 002")},
            format="multipart",
        )
        assert upload_resp.status_code == 201
        file_pk = upload_resp.json()["pk"]

        # PATCH assign category
        response = authenticated_client.patch(
            f"/api/pim/admin/files/{file_pk}/", {"file_category_code": "patch-cat"}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["category_code"] == "patch-cat"

    def test_patch_clear_category(self, authenticated_client):
        # Create category + upload + assign
        authenticated_client.post(
            "/api/pim/admin/files-categories/", {"code": "clear-cat", "name_t9n": {"en": "Clear Me"}}, format="json"
        )
        upload_resp = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": create_test_file(content=b"clear category content 003")},
            format="multipart",
        )
        file_pk = upload_resp.json()["pk"]
        authenticated_client.patch(
            f"/api/pim/admin/files/{file_pk}/", {"file_category_code": "clear-cat"}, format="json"
        )

        # PATCH clear category
        response = authenticated_client.patch(
            f"/api/pim/admin/files/{file_pk}/", {"file_category_code": None}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["category_code"] is None

    def test_upload_with_file_label_t9n(self, authenticated_client):
        file_obj = create_test_file(content=b"upload with t9n content 004")
        response = authenticated_client.post(
            "/api/pim/admin/files/upload/",
            {"file": file_obj, "file_label_t9n": '{"en": "Upload Label", "pl": "Etykieta"}'},
            format="multipart",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["file_label_t9n"] == {"en": "Upload Label", "pl": "Etykieta"}

    def test_patch_nonexistent_file_returns_404(self, authenticated_client):
        response = authenticated_client.patch(
            "/api/pim/admin/files/99999/", {"file_label_t9n": {"en": "Ghost"}}, format="json"
        )

        assert response.status_code == 404
