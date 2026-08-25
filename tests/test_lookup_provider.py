# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the django-lookup provider (plan 03).

The provider is PIM's read boundary for the lookup module. It is exercised directly — no
django_lookup dependency: the module mirrors the contract dataclasses on purpose.
"""

import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from django_pim.models import (
    Feature,
    FeatureScopeEnum,
    FeatureTypeEnum,
    PictureRoleEnum,
    ProductAttribute,
    ProductPicture,
)
from django_pim.services import lookup_provider
from django_pim.services.product_picture_service import upload_picture

from .factories import ChannelFactory, FeatureSetFactory, LanguageFactory, ProductFactory, RealProductFactory

pytestmark = pytest.mark.django_db


def _picture(color="red"):
    """HashedImageField needs a real file handle — go through the service, like the other suites."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=color).save(buffer, format="PNG")
    buffer.seek(0)
    return upload_picture(SimpleUploadedFile(f"{color}.png", buffer.read(), content_type="image/png"))


def _attribute(product, idx, *, t9n=None, txt=None, scope=FeatureScopeEnum.BUSINESS_UNIT):
    """`Feature.idx` is globally unique — reuse it when a sibling product already declared it."""
    feature_type = FeatureTypeEnum.VARCHAR255_T9N if t9n is not None else FeatureTypeEnum.VARCHAR255
    feature, _ = Feature.objects.get_or_create(idx=idx, defaults={"scope": scope, "feature_type": feature_type})
    return ProductAttribute.objects.create(product=product, feature=feature, value_txt_t9n=t9n, value_txt=txt)


@pytest.fixture
def product():
    channel = ChannelFactory(idx="main", default_language=LanguageFactory(iso2="PL"))
    real_product = RealProductFactory(sku="SKU-1", ean="5901234123457", weight=Decimal("1.20"))
    return ProductFactory(shop=channel, real_product=real_product, feature_set=FeatureSetFactory(), is_enabled=True)


def test_item_carries_identifiers_names_and_physicals(product):
    _attribute(product, "name", t9n={"pl": "Wiertarka", "en": "Drill", "de": ""}, scope=FeatureScopeEnum.SYSTEM)
    _attribute(product, "brand", t9n={"pl": "Bosch"}, scope=FeatureScopeEnum.SYSTEM)
    _attribute(product, lookup_provider.MPN_FEATURE_IDX, txt="GSR 12V-35")

    item = lookup_provider.get_item("SKU-1")

    assert item.ref == "SKU-1"
    assert item.gtin == "5901234123457"
    assert item.name_by_lang == {"pl": "Wiertarka", "en": "Drill"}  # empty translations dropped
    assert (item.brand, item.mpn) == ("Bosch", "GSR 12V-35")
    assert item.attrs == {"weight": Decimal("1.20"), "width": None, "height": None, "deep": None}
    assert item.updated_at == product.real_product.updated_at


def test_item_without_products_or_attributes_is_still_served(product):
    product.delete()

    item = lookup_provider.get_item("SKU-1")

    assert (item.name_by_lang, item.brand, item.mpn, item.image_path_or_url) == ({}, None, None, None)


def test_display_data_comes_from_the_first_enabled_product(product):
    disabled = ProductFactory(
        shop=ChannelFactory(idx="other", default_language=LanguageFactory(iso2="PL")),
        real_product=product.real_product,
        feature_set=FeatureSetFactory(),
        is_enabled=False,
    )
    _attribute(disabled, "name", t9n={"pl": "Stara nazwa"}, scope=FeatureScopeEnum.SYSTEM)
    _attribute(product, "name", t9n={"pl": "Wiertarka"}, scope=FeatureScopeEnum.SYSTEM)

    assert lookup_provider.get_item("SKU-1").name_by_lang == {"pl": "Wiertarka"}
    assert lookup_provider.detail_url("SKU-1") == "/api/pim/v2/admin/main/products/SKU-1/"


def test_detail_url_resolves_to_the_registered_product_detail_route(product):
    """`DETAIL_URL` is a hardcoded mirror of the real route — a route change must fail this test,
    not silently produce dead CMS links. `resolve()`, not `reverse()`: the v2 and legacy admin
    mounts share the `product-detail` name, so `reverse()` is ambiguous between them.
    """
    from django.urls import resolve

    from django_pim.api.admin.views.product_views import ProductViewSet

    match = resolve(lookup_provider.detail_url("SKU-1"))

    assert match.url_name == "product-detail"
    assert match.kwargs == {"channel_idx": "main", "sku": "SKU-1"}
    assert match.func.cls is ProductViewSet


def test_image_is_the_main_picture_local_path(product):
    picture = _picture()
    ProductPicture.objects.create(product=product, picture=picture, picture_role=PictureRoleEnum.MAIN)
    ProductPicture.objects.create(product=product, picture=_picture("blue"), picture_role=PictureRoleEnum.GENERAL)

    assert lookup_provider.get_item("SKU-1").image_path_or_url == picture.image.path
    assert lookup_provider.basic("SKU-1").image_url == picture.image.url


def test_basic_is_the_display_payload(product):
    """Name and brand come back in the SAME language — the display product's channel default (PL
    here), not a global fallback: a hit must never pair a Polish brand with an English name."""
    _attribute(product, "name", t9n={"en": "Drill", "pl": "Wiertarka"}, scope=FeatureScopeEnum.SYSTEM)
    _attribute(product, "brand", t9n={"pl": "Bosch"}, scope=FeatureScopeEnum.SYSTEM)

    basic = lookup_provider.basic("SKU-1")

    assert (basic.ref, basic.name, basic.brand, basic.gtin) == ("SKU-1", "Wiertarka", "Bosch", "5901234123457")
    assert basic.image_url == ""


def test_a_non_t9n_name_feature_is_keyed_under_the_channel_language(product):
    """`lookup_bridge._attribute_text` reads `value_txt` on the query side, so the fingerprint must
    carry it too — otherwise such an installation can never be matched by name."""
    _attribute(product, "name", txt="Wiertarka", scope=FeatureScopeEnum.SYSTEM)

    assert lookup_provider.get_item("SKU-1").name_by_lang == {"pl": "Wiertarka"}
    assert lookup_provider.basic("SKU-1").name == "Wiertarka"


class TestBatchDisplayCalls:
    """`basics`/`detail_urls` — the optional protocol extension lookup prefers over the singular
    pair (`django_lookup.providers.base`): one round trip per hit list instead of two per ref."""

    def test_batch_answers_match_the_singular_calls(self, product):
        _attribute(product, "name", t9n={"pl": "Wiertarka"}, scope=FeatureScopeEnum.SYSTEM)
        RealProductFactory(sku="SKU-2")

        assert lookup_provider.basics(["SKU-1", "SKU-2"]) == {
            "SKU-1": lookup_provider.basic("SKU-1"),
            "SKU-2": lookup_provider.basic("SKU-2"),
        }
        assert lookup_provider.detail_urls(["SKU-1"]) == {"SKU-1": lookup_provider.detail_url("SKU-1")}

    def test_unknown_refs_are_omitted_not_raised(self, product):  # noqa: ARG002 — fixture builds SKU-1
        assert lookup_provider.basics(["NOPE"]) == {}
        assert lookup_provider.detail_urls(["NOPE"]) == {}

    def test_a_ref_without_a_channel_is_omitted_from_detail_urls(self, product):
        """The batch equivalent of the `LookupError` `detail_url` raises — lookup drops the hit."""
        product.delete()

        assert set(lookup_provider.basics(["SKU-1"])) == {"SKU-1"}
        assert lookup_provider.detail_urls(["SKU-1"]) == {}


def test_iter_items_streams_the_catalog_and_honours_since(product):  # noqa: ARG001 — fixture builds SKU-1
    newer = RealProductFactory(sku="SKU-2")

    assert sorted(item.ref for item in lookup_provider.iter_items()) == ["SKU-1", "SKU-2"]
    assert [item.ref for item in lookup_provider.iter_items(since=newer.updated_at)] == ["SKU-2"]


def test_unknown_ref_raises_lookup_error():
    with pytest.raises(LookupError):
        lookup_provider.get_item("NOPE")


def test_detail_url_without_a_channel_raises_lookup_error(product):
    product.delete()

    with pytest.raises(LookupError):
        lookup_provider.detail_url("SKU-1")


def _resolver(model: str, signal: str = "post_save"):
    """The `ref` callable django-lookup connects for one sender — the public signal contract."""
    specs = [s for s in lookup_provider.signal_specs() if s["model"] == model and s["signal"] == signal]
    assert len(specs) == 1, f"expected exactly one {signal} spec for {model}"
    return specs[0]["ref"]


class TestSignalSpecs:
    def test_every_declared_sender_is_a_real_model(self):
        from django.apps import apps

        for spec in lookup_provider.signal_specs():
            assert apps.get_model(spec["model"]) is not None
            assert spec["signal"] in ("post_save", "post_delete")

    def test_real_product_resolves_to_its_sku(self, product):
        assert _resolver("django_pim.RealProduct")(product.real_product) == "SKU-1"

    def test_product_resolves_to_its_sku(self, product):
        assert _resolver("django_pim.Product")(product) == "SKU-1"

    def test_product_without_a_real_product_is_ignored(self):
        from django_pim.models import Product

        assert _resolver("django_pim.Product")(Product()) is None

    def test_no_spec_watches_columns(self):
        """`update_product` compensates for `bulk_create` with a `post_save` that skips `pre_save`.

        A `watch` list is evaluated against a pre-save snapshot, so declaring one here would filter
        that compensating send out and freeze the fingerprint on the CMS edit path.
        """
        assert [s for s in lookup_provider.signal_specs() if s.get("watch")] == []

    @pytest.mark.parametrize(
        ("feature_idx", "scope", "expected"),
        [
            ("name", FeatureScopeEnum.SYSTEM, "SKU-1"),
            ("brand", FeatureScopeEnum.SYSTEM, "SKU-1"),
            ("mpn", FeatureScopeEnum.BUSINESS_UNIT, "SKU-1"),
            ("color", FeatureScopeEnum.BUSINESS_UNIT, None),
        ],
    )
    def test_only_fingerprinted_features_refresh(self, product, feature_idx, scope, expected):
        attribute = _attribute(product, feature_idx, txt="x", scope=scope)

        assert _resolver("django_pim.ProductAttribute")(attribute) == expected

    def test_a_non_fingerprinted_attribute_short_circuits_with_no_query(self, product, django_assert_num_queries):
        """The common case (enrichment apply, admin edit, per-row importer): no joins at all."""
        attribute = _attribute(product, "color", txt="red", scope=FeatureScopeEnum.BUSINESS_UNIT)
        resolve = _resolver("django_pim.ProductAttribute")
        resolve(ProductAttribute.objects.get(pk=attribute.pk))  # warm the fingerprinted-ids cache

        fresh = ProductAttribute.objects.get(pk=attribute.pk)
        with django_assert_num_queries(0):
            assert resolve(fresh) is None

    def test_a_fingerprinted_attribute_needs_two_queries_not_three(self, product, django_assert_num_queries):
        """Down from 3 (feature, product, real_product) to 2 — the feature check is now cached."""
        attribute = _attribute(product, "brand", t9n={"pl": "Bosch"}, scope=FeatureScopeEnum.SYSTEM)
        resolve = _resolver("django_pim.ProductAttribute")
        resolve(ProductAttribute.objects.get(pk=attribute.pk))  # warm the fingerprinted-ids cache

        fresh = ProductAttribute.objects.get(pk=attribute.pk)
        with django_assert_num_queries(2):
            assert resolve(fresh) == "SKU-1"

    @pytest.mark.parametrize("signal", ["post_save", "post_delete"])
    def test_only_the_main_picture_refreshes(self, product, signal):
        main = ProductPicture.objects.create(product=product, picture=_picture(), picture_role=PictureRoleEnum.MAIN)
        general = ProductPicture.objects.create(
            product=product, picture=_picture("blue"), picture_role=PictureRoleEnum.GENERAL
        )
        resolve = _resolver("django_pim.ProductPicture", signal)

        assert (resolve(main), resolve(general)) == ("SKU-1", None)


@pytest.fixture
def refreshed_refs():
    """Refs django-lookup would refresh — its real resolver on the real `Product` post_save."""
    from django.db.models.signals import post_save

    from django_pim.models import Product

    refs: list[str | None] = []
    resolve = _resolver("django_pim.Product")

    def receiver(sender, instance, **kwargs):
        refs.append(resolve(instance))

    post_save.connect(receiver, sender=Product, weak=False, dispatch_uid="test-lookup-product-refresh")
    yield refs
    post_save.disconnect(sender=Product, dispatch_uid="test-lookup-product-refresh")


def test_renaming_a_product_refreshes_its_fingerprint(product, refreshed_refs):
    """The regression: `_set_product_attributes` bulk-creates, so only the Product sender sees it."""
    from django_pim.services import product_service

    _attribute(product, "name", t9n={"pl": "Wiertarka"}, scope=FeatureScopeEnum.SYSTEM)
    refreshed_refs.clear()

    product_service.update_product(
        product.shop.idx, "SKU-1", attributes=[{"feature_idx": "name", "value_txt_t9n": {"pl": "Szlifierka"}}]
    )

    assert refreshed_refs == ["SKU-1"]
    assert lookup_provider.get_item("SKU-1").name_by_lang == {"pl": "Szlifierka"}
