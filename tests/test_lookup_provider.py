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


def test_image_is_the_main_picture_local_path(product):
    picture = _picture()
    ProductPicture.objects.create(product=product, picture=picture, picture_role=PictureRoleEnum.MAIN)
    ProductPicture.objects.create(product=product, picture=_picture("blue"), picture_role=PictureRoleEnum.GENERAL)

    assert lookup_provider.get_item("SKU-1").image_path_or_url == picture.image.path
    assert lookup_provider.basic("SKU-1").image_url == picture.image.url


def test_basic_is_the_display_payload(product):
    _attribute(product, "name", t9n={"en": "Drill", "pl": "Wiertarka"}, scope=FeatureScopeEnum.SYSTEM)
    _attribute(product, "brand", t9n={"pl": "Bosch"}, scope=FeatureScopeEnum.SYSTEM)

    basic = lookup_provider.basic("SKU-1")

    assert (basic.ref, basic.name, basic.brand, basic.gtin) == ("SKU-1", "Drill", "Bosch", "5901234123457")
    assert basic.image_url == ""


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

    @pytest.mark.parametrize("signal", ["post_save", "post_delete"])
    def test_only_the_main_picture_refreshes(self, product, signal):
        main = ProductPicture.objects.create(product=product, picture=_picture(), picture_role=PictureRoleEnum.MAIN)
        general = ProductPicture.objects.create(
            product=product, picture=_picture("blue"), picture_role=PictureRoleEnum.GENERAL
        )
        resolve = _resolver("django_pim.ProductPicture", signal)

        assert (resolve(main), resolve(general)) == ("SKU-1", None)
