# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Every admin v2 error leaves in the v2 envelope, with the status it always had.

The views used to build ``{"detail": ...}`` by hand; now they raise DRF exceptions and the
shared v2 handler (django-utils) builds ``{error, message, debug_id, details[]}``. One row per
route and error path: the status is the pre-fix one, only the body changed.
"""

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from django_pim.models import Product, ProductLink
from django_pim.models.feature import FeatureScopeEnum
from tests.factories import (
    AttributesGroupFactory,
    FeatureFactory,
    FeatureInFeatureSetFactory,
    FeatureSetFactory,
    FilesCategoryFactory,
    GapDefinitionFactory,
    ProductCategoryFactory,
    ProductFactory,
    ProductLinkFactory,
    ProductLinkTypeFactory,
    RealProductFactory,
    ShopFactory,
)

V2 = "/api/pim/v2/admin"
CH = "v2err-main"
OTHER = "v2err-other"
SKU = "V2ERR-SKU-1"
ENVELOPE_KEYS = {"error", "message", "debug_id", "details"}


@pytest.fixture
def world(db):
    """One channel with one product and one of each named resource, plus a second channel."""
    channel = ShopFactory(idx=CH)
    ShopFactory(idx=OTHER)
    feature_set = FeatureSetFactory(idx="v2err-set")
    ProductFactory(shop=channel, feature_set=feature_set, real_product=RealProductFactory(sku=SKU))
    FeatureFactory(idx="v2err-feature")
    system = FeatureFactory(idx="v2err-system", scope=FeatureScopeEnum.SYSTEM)
    FeatureInFeatureSetFactory(feature_set=feature_set, feature=system)
    ProductCategoryFactory(shop=channel, idx="v2err-category")
    AttributesGroupFactory(idx="v2err-group")
    ProductLinkTypeFactory(idx="v2err-link-type")
    FilesCategoryFactory(code="v2err-files")
    GapDefinitionFactory(key="v2err-gap")
    return channel


def assert_envelope(response, status: int, error: str) -> dict:
    assert response.status_code == status, response.content
    body = response.json()
    assert set(body) == ENVELOPE_KEYS, body
    assert body["error"] == error
    assert body["message"]
    assert body["debug_id"]
    return body


NOT_FOUND = [
    # (method, path, payload)
    ("get", "gap-definitions/nope/", None),
    ("patch", "gap-definitions/nope/", {}),
    ("delete", "gap-definitions/nope/", None),
    ("get", f"{CH}/gaps/exemptions/?sku=NOPE", None),
    ("post", f"{CH}/gaps/exemptions/", {"sku": "NOPE", "definition_key": "nope"}),
    ("delete", f"{CH}/gaps/exemptions/999999/", None),
    ("get", "nope-channel/products/", None),
    ("get", f"{CH}/products/NOPE/", None),
    ("patch", f"{CH}/products/NOPE/", {}),
    ("delete", f"{CH}/products/NOPE/", None),
    ("post", "nope-channel/products/bulk/", {"skus": [SKU]}),
    ("post", f"{CH}/products/NOPE/copy-attributes/", {"source_channel_idx": OTHER}),
    ("post", f"{CH}/products/NOPE/add-to-channel/", {"target_channel_idx": OTHER}),
    (
        "post",
        f"{CH}/products/NOPE/toggle-override/",
        {"feature_idx": "v2err-feature", "language": "en", "override": True},
    ),
    ("post", f"{CH}/products/NOPE/toggle-media-override/", {"override": True}),
    ("get", "nope-channel/categories/", None),
    ("post", "nope-channel/categories/", {"idx": "v2err-new", "name_t9n": {"en": "New"}}),
    ("get", f"{CH}/categories/nope/", None),
    ("patch", f"{CH}/categories/nope/", {}),
    ("delete", f"{CH}/categories/nope/", None),
    ("patch", "nope-channel/categories/reorder/", {"items": [{"idx": "nope", "position": 1}]}),
    ("get", f"{CH}/categories/nope/products/", None),
    ("patch", f"{CH}/categories/nope/products/reorder/", {"items": [{"sku": SKU, "position": 1}]}),
    ("get", "nope-channel/features/", None),
    ("get", "features/nope/", None),
    ("patch", "features/nope/", {}),
    ("delete", "features/nope/", None),
    ("get", "features/nope/attributes/", None),
    ("get", "feature-sets/nope/", None),
    ("patch", "feature-sets/nope/", {}),
    ("delete", "feature-sets/nope/", None),
    ("get", "feature-sets/nope/features/", None),
    ("post", "feature-sets/nope/features/", {"features": [{"feature_idx": "v2err-feature"}]}),
    ("delete", "feature-sets/nope/features/", {"feature_idxs": ["v2err-feature"]}),
    ("patch", "feature-sets/nope/features/reorder/", {"features": [{"feature_idx": "v2err-feature", "position": 1}]}),
    ("patch", "feature-sets/nope/features/v2err-feature/", {"is_required": True}),
    ("get", "feature-sets/nope/required-features/", None),
    ("post", "attributes/", {"feature_idx": "nope", "idx": "red", "name_t9n": {"en": "Red"}}),
    ("get", "attributes/nope/nope/", None),
    ("patch", "attributes/nope/nope/", {}),
    ("delete", "attributes/nope/nope/", None),
    ("patch", "attributes/reorder/", {"items": [{"feature_idx": "nope", "idx": "nope", "display_order": 1}]}),
    ("get", "attributes-groups/nope/", None),
    ("patch", "attributes-groups/nope/", {}),
    ("delete", "attributes-groups/nope/", None),
    ("get", "link-types/nope/", None),
    ("patch", "link-types/nope/", {}),
    ("delete", "link-types/nope/", None),
    ("get", "files-categories/nope/", None),
    ("patch", "files-categories/nope/", {}),
    ("delete", "files-categories/nope/", None),
    ("get", f"{CH}/products/NOPE/links/", None),
    ("post", f"{CH}/products/NOPE/links/", {"linked_product_sku": SKU, "link_type_idx": "v2err-link-type"}),
    ("get", f"{CH}/products/{SKU}/links/999999/", None),
    ("patch", f"{CH}/products/{SKU}/links/999999/", {}),
    ("delete", f"{CH}/products/{SKU}/links/999999/", None),
    ("get", f"{CH}/products/NOPE/pictures/", None),
    ("post", f"{CH}/products/NOPE/pictures/", {"picture_pk": 999999}),
    ("get", f"{CH}/products/{SKU}/pictures/999999/", None),
    ("patch", f"{CH}/products/{SKU}/pictures/999999/", {}),
    ("delete", f"{CH}/products/{SKU}/pictures/999999/", None),
    ("patch", "files/999999/", {}),
    ("get", f"{CH}/products/NOPE/files/", None),
    ("post", f"{CH}/products/NOPE/files/", {"file_pk": 999999}),
    ("delete", f"{CH}/products/{SKU}/files/999999/", None),
    ("get", f"{CH}/products/NOPE/videos/", None),
    ("post", f"{CH}/products/NOPE/videos/", {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}),
    ("get", f"{CH}/products/{SKU}/videos/999999/", None),
    ("patch", f"{CH}/products/{SKU}/videos/999999/", {}),
    ("delete", f"{CH}/products/{SKU}/videos/999999/", None),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "path", "payload"), NOT_FOUND, ids=[f"{m} {p}" for m, p, _ in NOT_FOUND])
def test_not_found_is_v2_envelope(authenticated_client, world, method, path, payload):
    response = getattr(authenticated_client, method)(f"{V2}/{path}", payload, format="json")

    body = assert_envelope(response, 404, "NOT_FOUND")
    assert body["details"] == []


UNKNOWN_PARENT = [
    # Routes that answered 500 when the channel (or, on the nested detail routes, the product) did not exist.
    ("get", "nope-channel/feature-sets/", None),
    ("get", "nope-channel/feature-sets/v2err-set/", None),
    ("get", "nope-channel/feature-sets/v2err-set/features/", None),
    ("get", "nope-channel/attributes-groups/", None),
    *[
        (method, f"{channel}/products/{sku}/{child}/1/", payload)
        for channel, sku in (("nope-channel", SKU), (CH, "NOPE"))
        for child in ("pictures", "videos", "links")
        for method, payload in (("get", None), ("patch", {}), ("delete", None))
        if not (child == "links" and method == "get")  # links retrieve already caught both
    ],
    ("delete", f"nope-channel/products/{SKU}/files/1/", None),
    ("delete", f"{CH}/products/NOPE/files/1/", None),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "path", "payload"), UNKNOWN_PARENT, ids=[f"{m} {p}" for m, p, _ in UNKNOWN_PARENT])
def test_unknown_channel_or_product_is_404(authenticated_client, world, method, path, payload):
    response = getattr(authenticated_client, method)(f"{V2}/{path}", payload, format="json")

    assert_envelope(response, 404, "NOT_FOUND")


BAD_REQUEST = [
    # (method, path, payload, text in details[].description)
    ("get", "gap-definitions/?ordering=bogus", None, "ordering"),
    ("post", "gap-definitions/", {"key": "v2err-gap", "check_key": "bogus", "severity": "critical"}, "bogus"),
    ("patch", "gap-definitions/v2err-gap/", {"check_key": "bogus"}, "bogus"),
    ("get", f"{CH}/gaps/findings/?product_ids=1&severity=fatal", None, "fatal"),
    ("post", f"{CH}/gaps/exemptions/", {"sku": SKU, "definition_key": "v2err-gap", "language": "xx"}, "xx"),
    ("get", f"{CH}/products/?gap_severity=fatal", None, "fatal"),
    ("post", f"{CH}/products/", {"sku": SKU, "feature_set_idx": "v2err-set"}, "already exists"),
    ("post", f"{CH}/products/{SKU}/copy-attributes/", {"source_channel_idx": CH}, "cannot be the same"),
    (
        "post",
        f"{CH}/products/{SKU}/toggle-override/",
        {"feature_idx": "v2err-feature", "language": "en", "override": True},
        "",
    ),
    ("post", f"{CH}/products/{SKU}/toggle-media-override/", {"override": True}, ""),
    ("post", f"{CH}/categories/", {"idx": "v2err-category", "name_t9n": {"en": "Dup"}}, "already exists"),
    ("patch", f"{CH}/categories/v2err-category/", {"parent_category_idx": "v2err-category"}, ""),
    ("post", "features/", {"idx": "v2err-feature", "name_t9n": {"en": "Dup"}}, "already exists"),
    ("patch", "features/v2err-system/", {"feature_type": 1}, ""),
    ("delete", "features/v2err-system/", None, ""),
    ("post", "feature-sets/", {"idx": "v2err-set"}, "already exists"),
    ("patch", "feature-sets/v2err-set/features/v2err-system/", {"is_required": True}, "system"),
    ("post", "attributes-groups/", {"idx": "v2err-group", "name_t9n": {"en": "Dup"}}, "already exists"),
    ("post", "link-types/", {"idx": "v2err-link-type", "name_t9n": {"en": "Dup"}}, "already exists"),
    ("post", "files-categories/", {"code": "v2err-files", "name_t9n": {"en": "Dup"}}, "already exists"),
    ("post", f"{CH}/products/{SKU}/links/", {"linked_product_sku": SKU, "link_type_idx": "v2err-link-type"}, ""),
]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "path", "payload", "text"), BAD_REQUEST, ids=[f"{m} {p}" for m, p, _, _ in BAD_REQUEST]
)
def test_bad_request_is_v2_envelope(authenticated_client, world, method, path, payload, text):
    response = getattr(authenticated_client, method)(f"{V2}/{path}", payload, format="json")

    body = assert_envelope(response, 400, "VALIDATION_ERROR")
    descriptions = " ".join(d["description"] for d in body["details"])
    assert body["details"], body
    assert text in descriptions


@pytest.mark.django_db
class TestGapFindingsQuery:
    """The finding behind this fix: the docs explorer called ``gaps/findings/`` without ``product_ids``."""

    url = f"{V2}/{CH}/gaps/findings/"

    @pytest.mark.parametrize(
        ("query", "text"),
        [
            ("", "product_ids is required"),
            ("?product_ids=", "product_ids is required"),
            ("?product_ids=,", "product_ids is required"),
            ("?product_ids=a,b", "comma-separated list of integers"),
            ("?product_ids=" + ",".join(str(n) for n in range(1, 202)), "at most 200"),
        ],
    )
    def test_bad_product_ids_name_the_query_parameter(self, authenticated_client, world, query, text):
        body = assert_envelope(authenticated_client.get(self.url + query), 400, "VALIDATION_ERROR")

        assert [(d["field"], d["location"]) for d in body["details"]] == [("product_ids", "query")]
        assert text in body["details"][0]["description"]

    def test_valid_product_ids_answer_200(self, authenticated_client, world):
        response = authenticated_client.get(self.url + "?product_ids=1,2")

        assert response.status_code == 200
        assert response.json() == {"results": {}}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "field"),
    [
        (f"{CH}/gaps/exemptions/", "sku"),
        ("features/?scope=x", "scope"),
        ("features/?feature_type=x", "feature_type"),
        (f"{CH}/categories/?parent_category=x", "parent_category"),
    ],
)
def test_bad_query_parameter_is_named(authenticated_client, world, path, field):
    body = assert_envelope(authenticated_client.get(f"{V2}/{path}"), 400, "VALIDATION_ERROR")

    assert [(d["field"], d["location"]) for d in body["details"]] == [(field, "query")]


@pytest.mark.django_db
class TestLinkUpdate:
    """PATCH links/{pk}/ answered 500 for an unknown link type and for a type that duplicates another link."""

    @pytest.fixture
    def links(self, world):
        product = Product.objects.get(shop=world, real_product__sku=SKU)
        linked = ProductFactory(shop=world, real_product=RealProductFactory(sku="V2ERR-SKU-3"))
        related = ProductLinkFactory(product=product, linked_product=linked, link_type__idx="v2err-related")
        ProductLinkFactory(product=product, linked_product=linked, link_type__idx="v2err-crosssell")
        return f"{V2}/{CH}/products/{SKU}/links/{related.pk}/"

    @staticmethod
    def _stored_type(url: str) -> str:
        return ProductLink.objects.get(pk=url.rstrip("/").rsplit("/", 1)[1]).link_type.idx

    def test_unknown_link_type_is_404(self, authenticated_client, links):
        response = authenticated_client.patch(links, {"link_type_idx": "nope"}, format="json")

        assert_envelope(response, 404, "NOT_FOUND")
        assert self._stored_type(links) == "v2err-related"

    def test_duplicate_link_type_is_400(self, authenticated_client, links):
        response = authenticated_client.patch(links, {"link_type_idx": "v2err-crosssell"}, format="json")

        body = assert_envelope(response, 400, "VALIDATION_ERROR")
        assert "already exists" in body["details"][0]["description"]
        assert self._stored_type(links) == "v2err-related"

    def test_duplicate_lost_to_a_concurrent_request_is_400(self, authenticated_client, links):
        with patch("django_pim.services.product_link_service._is_duplicate", return_value=False):
            response = authenticated_client.patch(links, {"link_type_idx": "v2err-crosssell"}, format="json")

        body = assert_envelope(response, 400, "VALIDATION_ERROR")
        assert "already exists" in body["details"][0]["description"]
        assert self._stored_type(links) == "v2err-related"

    def test_service_refuses_fields_outside_the_whitelist(self, links):
        from django_pim.services import update_product_link

        other = ProductFactory(shop=ShopFactory(idx=CH), real_product=RealProductFactory(sku="V2ERR-SKU-4"))
        pk = int(links.rstrip("/").rsplit("/", 1)[1])

        with pytest.raises(ValueError, match="not editable"):
            update_product_link(channel_idx=CH, sku=SKU, pk=pk, linked_product=other)

    def test_empty_link_type_is_400_like_create(self, authenticated_client, links):
        response = authenticated_client.patch(links, {"link_type_idx": ""}, format="json")

        body = assert_envelope(response, 400, "VALIDATION_ERROR")
        assert body["details"][0]["field"] == "link_type_idx"

    def test_new_link_type_is_saved(self, authenticated_client, links):
        ProductLinkTypeFactory(idx="v2err-upsell")

        response = authenticated_client.patch(links, {"link_type_idx": "v2err-upsell"}, format="json")

        assert response.status_code == 200, response.content
        assert response.json()["link_type_idx"] == "v2err-upsell"


@pytest.mark.django_db
def test_add_to_channel_conflict_keeps_its_message(authenticated_client, world):
    real_product = RealProductFactory(sku="V2ERR-SKU-2")
    ProductFactory(shop=world, real_product=real_product)
    ProductFactory(shop=ShopFactory(idx=OTHER), real_product=real_product)

    response = authenticated_client.post(
        f"{V2}/{CH}/products/V2ERR-SKU-2/add-to-channel/", {"target_channel_idx": OTHER}, format="json"
    )

    body = assert_envelope(response, 409, "CONFLICT")
    assert "already exists" in body["message"]


@pytest.mark.django_db
class TestUploads:
    @pytest.fixture(autouse=True)
    def _media_in_tmp(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)

    def test_picture_upload_without_image(self, authenticated_client, world):
        response = authenticated_client.post(f"{V2}/pictures/upload/", {}, format="multipart")

        body = assert_envelope(response, 400, "VALIDATION_ERROR")
        assert "image" in body["details"][0]["description"]

    def test_file_upload_without_file(self, authenticated_client, world):
        response = authenticated_client.post(f"{V2}/files/upload/", {}, format="multipart")

        body = assert_envelope(response, 400, "VALIDATION_ERROR")
        assert "file" in body["details"][0]["description"]

    @pytest.mark.parametrize(("label", "text"), [("{not json", "Invalid JSON"), ('["en"]', "JSON object")])
    def test_file_upload_bad_label(self, authenticated_client, world, label, text):
        upload = SimpleUploadedFile("manual.pdf", b"%PDF-1.4 test", content_type="application/pdf")

        response = authenticated_client.post(
            f"{V2}/files/upload/", {"file": upload, "file_label_t9n": label}, format="multipart"
        )

        body = assert_envelope(response, 400, "VALIDATION_ERROR")
        assert text in body["details"][0]["description"]

    def test_file_update_unknown_category(self, authenticated_client, world):
        upload = SimpleUploadedFile("manual.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        created = authenticated_client.post(f"{V2}/files/upload/", {"file": upload}, format="multipart")
        assert created.status_code == 201, created.content
        pk = created.json()["pk"]

        response = authenticated_client.patch(f"{V2}/files/{pk}/", {"file_category_code": "nope"}, format="json")

        body = assert_envelope(response, 400, "VALIDATION_ERROR")
        assert "nope" in body["details"][0]["description"]


@pytest.mark.django_db
def test_internal_error_is_v2_envelope_without_internals(authenticated_client, world):
    with patch(
        "django_pim.api.admin.views.gaps_views.get_findings_for_products",
        side_effect=RuntimeError("secret db dsn postgres://user:pw@host/db"),
    ):
        response = authenticated_client.get(f"{V2}/{CH}/gaps/findings/?product_ids=1")

    body = assert_envelope(response, 500, "INTERNAL_ERROR")
    assert body["details"] == []
    assert "secret" not in response.content.decode()
    assert "postgres" not in response.content.decode()
