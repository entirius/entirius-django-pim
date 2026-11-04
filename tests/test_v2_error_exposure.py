# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""No exception text reaches an admin v2 response (CodeQL py/stack-trace-exposure).

One row per route CodeQL flagged. The view's service is mocked: a ``ValueError`` from a lower layer answers the
generic 500 (an error id, never its message); a refusal the module wrote (``InvalidRequestError``) keeps the
status and the message it had in 3.6.0. A 404 never carries exception text: the v2 handler answers its own sentence.
"""

from unittest.mock import patch

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile

from django_pim.exceptions import InvalidRequestError
from django_pim.models import FeatureTypeEnum, Product, ProductAttribute
from tests.factories import FeatureFactory
from tests.test_admin_api_v2_errors import CH, OTHER, SKU, V2, world  # noqa: F401 (world: fixture)

pytestmark = pytest.mark.usefixtures("world")

# What a driver or SDK error carries: a path, a host, a token. None of it may reach a client.
LEAK = "OperationalError: /srv/app/.env token=sk-leak-4f2a host=db-internal"
REFUSAL = "Refused by the PIM for this test"

VIEWS = "django_pim.api.admin.views"
PRODUCT = f"{CH}/products/{SKU}"

# (alert numbers, method, path, payload, patched service, status of a module refusal)
ROUTES = [
    ("50", "post", "attributes-groups/", {"idx": "new-group", "name_t9n": {"en": "G"}}, "attributes_group_views.create_attributes_group", 400),
    ("49", "post", "attributes/", {"feature_idx": "v2err-feature", "idx": "red", "name_t9n": {"en": "Red"}}, "attribute_views.create_attribute", 400),
    ("51", "get", f"{CH}/categories/", None, "category_views.list_categories", 400),
    ("52", "post", f"{CH}/categories/", {"idx": "v2err-new", "name_t9n": {"en": "New"}}, "category_views.create_category", 400),
    ("53", "patch", f"{CH}/categories/v2err-category/", {"name_t9n": {"en": "X"}}, "category_views.update_category", 400),
    ("54", "patch", f"{CH}/categories/reorder/", {"items": [{"idx": "v2err-category", "position": 1}]}, "category_views.reorder_categories", 400),
    ("57", "get", "feature-sets/", None, "feature_set_views.list_feature_sets", 400),
    ("58", "post", "feature-sets/", {"idx": "v2err-new-set"}, "feature_set_views.create_feature_set", 400),
    ("59", "patch", "feature-sets/v2err-set/", {"name": "X"}, "feature_set_views.update_feature_set", 400),
    ("60", "post", "feature-sets/v2err-set/features/", {"features": [{"feature_idx": "v2err-feature"}]}, "feature_set_views.bulk_add_features_to_set", 400),
    ("63", "patch", "feature-sets/v2err-set/features/v2err-system/", {"is_required": True}, "feature_set_views.set_feature_required_override", 400),
    ("55", "get", "features/", None, "feature_views.list_features", 400),
    ("56", "post", "features/", {"idx": "v2err-new-feature", "name_t9n": {"en": "N"}}, "feature_views.create_feature", 400),
    ("61", "patch", "features/v2err-feature/", {"name_t9n": {"en": "X"}}, "feature_views.update_feature", 400),
    ("62", "delete", "features/v2err-feature/", None, "feature_views.delete_feature", 400),
    ("64", "post", "files-categories/", {"code": "new-files", "name_t9n": {"en": "N"}}, "files_category_views.create_files_category", 400),
    ("65", "get", "gap-definitions/", None, "gaps_views.list_gap_definitions", 400),
    ("66", "post", "gap-definitions/", {"key": "new-gap", "check_key": "feature_present", "severity": "critical", "params": {"feature_idx": "v2err-feature"}}, "gaps_views.create_gap_definition", 400),
    ("67", "patch", "gap-definitions/v2err-gap/", {"severity": "warning"}, "gaps_views.update_gap_definition", 400),
    ("68", "get", f"{CH}/gaps/findings/?product_ids=1", None, "gaps_views.get_findings_for_products", 400),
    ("70", "get", f"{CH}/gaps/exemptions/?sku={SKU}", None, "gaps_views.list_exemptions", 400),
    ("72", "post", f"{CH}/gaps/exemptions/", {"sku": SKU, "definition_key": "v2err-gap"}, "gaps_views.create_exemption", 400),
    ("74", "post", f"{PRODUCT}/files/", {"file_pk": 1}, "product_file_views.link_file_to_product", 400),
    ("75", "get", f"{CH}/categories/v2err-category/products/", None, "product_in_category_views.list_products_in_category", 400),
    ("76", "patch", f"{CH}/categories/v2err-category/products/reorder/", {"items": [{"sku": SKU, "position": 1}]}, "product_in_category_views.reorder_products_in_category", 400),
    ("77", "post", "link-types/", {"idx": "new-link-type", "name_t9n": {"en": "N"}}, "product_link_type_views.create_product_link_type", 400),
    ("78", "post", f"{PRODUCT}/links/", {"linked_product_sku": SKU, "link_type_idx": "v2err-link-type"}, "product_link_views.create_product_link", 400),
    ("79", "patch", f"{PRODUCT}/links/1/", {"position": 2}, "product_link_views.update_product_link", 400),
    ("80", "post", f"{PRODUCT}/pictures/", {"picture_pk": 1}, "product_picture_views.link_picture_to_product", 400),
    ("81", "patch", f"{PRODUCT}/pictures/1/", {"position": 2}, "product_picture_views.update_product_picture", 400),
    ("82", "post", f"{PRODUCT}/videos/", {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, "product_video_views.create_product_video", 400),
    ("83", "patch", f"{PRODUCT}/videos/1/", {"position": 2}, "product_video_views.update_product_video", 400),
    ("84", "get", f"{CH}/products/", None, "product_views.list_products", 400),
    ("85", "post", f"{CH}/products/", {"sku": "V2ERR-NEW", "feature_set_idx": "v2err-set"}, "product_views.create_product", 400),
    ("86", "patch", f"{PRODUCT}/", {"is_enabled": False}, "product_views.update_product", 400),
    ("87", "post", f"{CH}/products/bulk/", {"skus": [SKU], "is_enabled": False}, "product_views.bulk_update_products", 400),
    ("88", "post", f"{PRODUCT}/add-to-channel/", {"target_channel_idx": OTHER}, "product_views.add_product_to_channel", 409),
    ("89", "post", f"{PRODUCT}/toggle-override/", {"feature_idx": "v2err-feature", "language": "en", "override": True}, "product_views.toggle_language_override", 400),
    ("90", "post", f"{PRODUCT}/toggle-media-override/", {"override": True, "picture_id": 1}, "product_views.toggle_media_override", 400),
]  # fmt: skip
IDS = [f"#{alert} {method} {path}" for alert, method, path, *_ in ROUTES]
PREFIXED = {"feature_set_views.list_feature_sets", "feature_views.list_features"}  # "Invalid parameter: <message>"
ERROR_CODES = {400: "VALIDATION_ERROR", 409: "CONFLICT"}

# Gap exemptions turned an ObjectDoesNotExist into NotFound(str(exc)).
NOT_FOUND_ROUTES = [
    ("69", "get", f"{CH}/gaps/exemptions/?sku={SKU}", None, "gaps_views.list_exemptions"),
    (
        "71",
        "post",
        f"{CH}/gaps/exemptions/",
        {"sku": SKU, "definition_key": "v2err-gap"},
        "gaps_views.create_exemption",
    ),
    ("73", "delete", f"{CH}/gaps/exemptions/1/", None, "gaps_views.delete_exemption"),
]
NOT_FOUND_IDS = [f"#{alert} {method} {path}" for alert, method, path, *_ in NOT_FOUND_ROUTES]


def _call(client, method: str, path: str, payload: dict | None, target: str, error: Exception):
    with patch(f"{VIEWS}.{target}", side_effect=error) as service:
        response = getattr(client, method)(f"{V2}/{path}", payload, format="json")
    assert service.called, f"{target} not reached: {response.status_code} {response.content!r}"
    return response


def _assert_no_leak(response) -> None:
    assert b"sk-leak" not in response.content
    assert b"/srv/app" not in response.content


def _assert_generic_500(response) -> None:
    assert response.status_code == 500, response.content
    body = response.json()
    assert body["error"] == "INTERNAL_ERROR"
    assert body["message"] == "An internal error occurred."
    assert body["debug_id"]
    assert body["details"] == []
    _assert_no_leak(response)


def _text(body: dict) -> str:
    return " ".join([body["message"], *(d["description"] for d in body["details"])])


@pytest.mark.django_db
@pytest.mark.parametrize(("alert", "method", "path", "payload", "target", "refusal_status"), ROUTES, ids=IDS)
def test_lower_layer_value_error_is_a_generic_500(
    authenticated_client, alert, method, path, payload, target, refusal_status
):
    _assert_generic_500(_call(authenticated_client, method, path, payload, target, ValueError(LEAK)))


@pytest.mark.django_db
@pytest.mark.parametrize(("alert", "method", "path", "payload", "target", "refusal_status"), ROUTES, ids=IDS)
def test_module_refusal_keeps_status_and_message(
    authenticated_client, alert, method, path, payload, target, refusal_status
):
    response = _call(authenticated_client, method, path, payload, target, InvalidRequestError(REFUSAL))

    assert response.status_code == refusal_status, response.content
    body = response.json()
    assert body["error"] == ERROR_CODES[refusal_status]
    expected = f"Invalid parameter: {REFUSAL}" if target in PREFIXED else REFUSAL
    assert expected in _text(body)


@pytest.mark.django_db
@pytest.mark.parametrize(("alert", "method", "path", "payload", "target"), NOT_FOUND_ROUTES, ids=NOT_FOUND_IDS)
def test_lower_layer_does_not_exist_hides_its_message(authenticated_client, alert, method, path, payload, target):
    response = _call(authenticated_client, method, path, payload, target, ObjectDoesNotExist(LEAK))

    assert response.status_code == 404, response.content
    assert response.json()["error"] == "NOT_FOUND"
    _assert_no_leak(response)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "field"),
    [
        (f"{CH}/products/?visibility=x", "visibility"),
        (f"{CH}/products/?product_class=x", "product_class"),
        (f"{CH}/categories/v2err-category/products/?page=x", "page"),
        (f"{CH}/categories/v2err-category/products/?page_size=x", "page_size"),
        (f"{CH}/categories/v2err-category/products/?page=0", "page"),
        (f"{CH}/categories/v2err-category/products/?page_size=-5", "page_size"),
    ],
)
def test_non_integer_query_parameter_is_a_named_400(authenticated_client, path, field):
    response = authenticated_client.get(f"{V2}/{path}")

    assert response.status_code == 400, response.content
    assert [(d["field"], d["location"]) for d in response.json()["details"]] == [(field, "query")]


@pytest.mark.django_db
def test_non_integer_picture_position_is_a_named_400(authenticated_client):
    image = SimpleUploadedFile("x.png", b"not-really-a-png", content_type="image/png")
    with patch(f"{VIEWS}.product_picture_views.upload_picture") as upload:
        response = authenticated_client.post(
            f"{V2}/{PRODUCT}/pictures/", {"image": image, "position": "x"}, format="multipart"
        )

    assert response.status_code == 400, response.content
    assert [d["field"] for d in response.json()["details"]] == ["position"]
    assert not upload.called  # refused before a Picture is stored


@pytest.mark.django_db
def test_file_upload_with_unknown_file_type_is_a_400(authenticated_client):
    pdf = SimpleUploadedFile("x.pdf", b"%PDF-1.4 synthetic", content_type="application/pdf")

    response = authenticated_client.post(f"{V2}/files/upload/", {"file": pdf, "file_type": "bogus"}, format="multipart")

    assert response.status_code == 400, response.content
    assert "Invalid file type: 'bogus'" in _text(response.json())


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "payload", "text"),
    [
        ("features/", {"idx": "Not A Slug", "name_t9n": {"en": "N"}}, "idx must be slugify"),
        (f"{CH}/products/", {"sku": "A,B", "feature_set_idx": "v2err-set"}, "forbidden character"),
    ],
)
def test_idx_normalizator_refusal_stays_a_400(authenticated_client, path, payload, text):
    response = authenticated_client.post(f"{V2}/{path}", payload, format="json")

    assert response.status_code == 400, response.content
    assert text in _text(response.json())


@pytest.mark.django_db
def test_product_attribute_invariant_stays_a_400(authenticated_client):
    """``ProductAttribute.save()`` refuses a row without its value: a 400 with its text, as in 3.6.0."""
    product = Product.objects.get(real_product__sku=SKU)
    feature = FeatureFactory(idx="v2err-no-value", feature_type=FeatureTypeEnum.VARCHAR255)
    ProductAttribute.objects.bulk_create([ProductAttribute(product=product, feature=feature)])
    Product.objects.filter(pk=product.pk).update(inherit_attributes=True)

    response = authenticated_client.post(
        f"{V2}/{PRODUCT}/toggle-override/",
        {"feature_idx": "v2err-no-value", "language": "en", "override": True},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "value_txt can not be None" in _text(response.json())
