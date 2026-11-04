# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The OpenAPI 200 of every admin list operation describes the body the view really returns.

drf-spectacular describes the 200 of a ``list`` action as an array of its response model, while the views answer
one object (a page ``{count, next, previous, results}``, ``{results}``, or category products'
``{positioned, unpositioned, ...}``). Each case fetches a real, non-empty response and validates it against the
generated schema. The legacy ``/api/pim/admin/`` operations are the same views and models.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from jsonschema import Draft202012Validator
from PIL import Image

from tests.factories import (
    AttributeFactory,
    AttributesGroupFactory,
    FeatureFactory,
    FeatureInFeatureSetFactory,
    FeatureSetFactory,
    FilesCategoryFactory,
    GapDefinitionFactory,
    GapExemptionFactory,
    GapFindingFactory,
    ProductCategoryFactory,
    ProductFactory,
    ProductInCategoryFactory,
    ProductLinkFactory,
    ProductLinkTypeFactory,
    RealProductFactory,
    ShopFactory,
)

V2 = "/api/pim/v2/admin"
CH = "lists-main"
SKU = "LISTS-SKU-1"

# (OpenAPI path, concrete URL); {pk} is filled with the first product's pk.
LIST_OPERATIONS = [
    ("/api/pim/v2/admin/{channel_idx}/attributes-groups/", f"{CH}/attributes-groups/"),
    ("/api/pim/v2/admin/{channel_idx}/categories/", f"{CH}/categories/"),
    ("/api/pim/v2/admin/{channel_idx}/categories/{idx}/products/", f"{CH}/categories/lists-category/products/"),
    ("/api/pim/v2/admin/{channel_idx}/feature-sets/", f"{CH}/feature-sets/"),
    ("/api/pim/v2/admin/{channel_idx}/features/", f"{CH}/features/"),
    ("/api/pim/v2/admin/{channel_idx}/gaps/exemptions/", f"{CH}/gaps/exemptions/?sku={SKU}"),
    ("/api/pim/v2/admin/{channel_idx}/gaps/findings/", f"{CH}/gaps/findings/?product_ids={{pk}}"),
    ("/api/pim/v2/admin/{channel_idx}/products/", f"{CH}/products/"),
    ("/api/pim/v2/admin/{channel_idx}/products/{sku}/files/", f"{CH}/products/{SKU}/files/"),
    ("/api/pim/v2/admin/{channel_idx}/products/{sku}/links/", f"{CH}/products/{SKU}/links/"),
    ("/api/pim/v2/admin/{channel_idx}/products/{sku}/pictures/", f"{CH}/products/{SKU}/pictures/"),
    ("/api/pim/v2/admin/{channel_idx}/products/{sku}/videos/", f"{CH}/products/{SKU}/videos/"),
    ("/api/pim/v2/admin/attributes/", "attributes/"),
    ("/api/pim/v2/admin/attributes-groups/", "attributes-groups/"),
    ("/api/pim/v2/admin/channels/", "channels/"),
    ("/api/pim/v2/admin/feature-sets/", "feature-sets/"),
    ("/api/pim/v2/admin/features/", "features/"),
    ("/api/pim/v2/admin/files-categories/", "files-categories/"),
    ("/api/pim/v2/admin/gap-definitions/", "gap-definitions/"),
    ("/api/pim/v2/admin/link-types/", "link-types/"),
]


@pytest.fixture(scope="module")
def schema():
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def _image() -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), color="navy").save(buffer, format="JPEG")
    return SimpleUploadedFile("lists.jpg", buffer.getvalue(), content_type="image/jpeg")


@pytest.fixture
def catalog(db, authenticated_client, settings, tmp_path):
    """One of everything a list view returns, so no list is empty."""
    settings.MEDIA_ROOT = str(tmp_path)
    channel = ShopFactory(idx=CH)
    feature_set = FeatureSetFactory(idx="lists-set")
    feature = FeatureFactory(idx="lists-feature")
    FeatureInFeatureSetFactory(feature_set=feature_set, feature=feature)
    AttributeFactory(feature=feature, idx="lists-attribute")
    AttributesGroupFactory(idx="lists-group")
    product = ProductFactory(shop=channel, feature_set=feature_set, real_product=RealProductFactory(sku=SKU))
    linked = ProductFactory(shop=channel, feature_set=feature_set, real_product=RealProductFactory(sku="LISTS-SKU-2"))
    ProductLinkFactory(product=product, linked_product=linked, link_type=ProductLinkTypeFactory(idx="lists-related"))
    category = ProductCategoryFactory(shop=channel, idx="lists-category")
    ProductInCategoryFactory(product=product, category=category, position=1)
    ProductInCategoryFactory(product=linked, category=category, position=0)
    FilesCategoryFactory(code="lists-files")
    definition = GapDefinitionFactory(key="lists-gap")
    GapFindingFactory(product=product, definition=definition)
    GapExemptionFactory(product=product, definition=GapDefinitionFactory(key="lists-muted"))

    base = f"{V2}/{CH}/products/{SKU}"
    picture = authenticated_client.post(f"{V2}/pictures/upload/", {"image": _image()}, format="multipart")
    upload = SimpleUploadedFile("lists.pdf", b"%PDF-1.4 lists", content_type="application/pdf")
    file = authenticated_client.post(f"{V2}/files/upload/", {"file": upload}, format="multipart")
    assert [picture.status_code, file.status_code] == [201, 201], [picture.content, file.content]
    created = [
        authenticated_client.post(f"{base}/pictures/", {"picture_pk": picture.json()["pk"]}, format="json"),
        authenticated_client.post(f"{base}/files/", {"file_pk": file.json()["pk"]}, format="json"),
        authenticated_client.post(f"{base}/videos/", {"video_url": "https://vimeo.com/76979871"}, format="json"),
    ]
    assert [r.status_code for r in created] == [201, 201, 201], [r.content for r in created]
    return product


def _validator(schema: dict, path: str) -> Draft202012Validator:
    body = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    return Draft202012Validator({**body, "components": schema["components"]})


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "url"), LIST_OPERATIONS, ids=[path for path, _ in LIST_OPERATIONS])
def test_list_response_matches_its_schema(authenticated_client, schema, catalog, path, url):
    response = authenticated_client.get(f"{V2}/{url.format(pk=catalog.pk)}")

    assert response.status_code == 200, response.content
    body = response.json()
    assert isinstance(body, dict)
    assert body.get("results") or (body.get("positioned") and body.get("unpositioned")), body  # real items
    errors = [f"{list(e.absolute_path)}: {e.message}" for e in _validator(schema, path).iter_errors(body)]
    assert errors == []


def test_no_operation_describes_its_200_as_a_bare_array(schema):
    """A new list action whose model lacks `@list_body` shows up here before it reaches the docs."""
    wrapped = [
        f"{method.upper()} {path}"
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if operation.get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("type")
        == "array"
    ]

    assert wrapped == []
