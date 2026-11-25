# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Product url_key: generated on create, copied by add-to-channel, filled by ``pim_fill_url_keys``."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from django_pim.models import FeatureScopeEnum, FeatureTypeEnum, Product, ProductAttribute
from django_pim.services import product_service
from django_pim.services.inheritance_service import add_product_to_channel, copy_translations
from tests.factories import (
    ChannelFactory,
    FeatureFactory,
    FeatureSetFactory,
    ProductFactory,
    RealProductFactory,
)

pytestmark = pytest.mark.django_db

T9N = FeatureTypeEnum.VARCHAR255_T9N
NAME = {"en": "Big Chair", "pl": "Duze Krzeslo"}


@pytest.fixture
def name_feature():
    return FeatureFactory(idx="name", feature_type=T9N, scope=FeatureScopeEnum.SYSTEM)


@pytest.fixture
def url_key_feature():
    return FeatureFactory(idx="url_key", feature_type=T9N, scope=FeatureScopeEnum.SYSTEM)


@pytest.fixture
def channel_a():
    return ChannelFactory(idx="uk-a")


@pytest.fixture
def channel_b():
    return ChannelFactory(idx="uk-b")


@pytest.fixture
def feature_set():
    return FeatureSetFactory(idx="uk-set")


def _create(sku: str, attributes: list[dict], channel_idx: str = "uk-a") -> Product:
    return product_service.create_product(
        channel_idx=channel_idx, sku=sku, feature_set_idx="uk-set", attributes=attributes
    )


def _name(value: dict = NAME) -> dict:
    return {"feature_idx": "name", "value_txt_t9n": value}


def _url_keys(product: Product) -> dict:
    row = ProductAttribute.objects.filter(product=product, feature__idx="url_key").first()
    return row.value_txt_t9n if row else {}


def _stored_product(channel, sku: str, name: dict | None, name_feature, url_key: dict | None = None, url_feature=None):
    product = ProductFactory(shop=channel, real_product=RealProductFactory(sku=sku), feature_set=FeatureSetFactory())
    if name is not None:
        ProductAttribute.objects.create(product=product, feature=name_feature, value_txt_t9n=name)
    if url_key is not None:
        ProductAttribute.objects.create(product=product, feature=url_feature, value_txt_t9n=url_key)
    return product


class TestCreate:
    def test_generated_per_language_with_a_name(self, channel_a, feature_set, name_feature, url_key_feature):
        product = _create("AB/12", [_name({"en": "Big Chair", "pl": "Duze Krzeslo", "de": "  "})])

        assert _url_keys(product) == {"en": "big-chair-ab-12", "pl": "duze-krzeslo-ab-12"}

    def test_given_key_is_never_overwritten(self, channel_a, feature_set, name_feature, url_key_feature):
        attributes = [_name(), {"feature_idx": "url_key", "value_txt_t9n": {"en": "my-own-key"}}]

        product = _create("SKU-1", attributes)

        # en is given, pl is empty and gets filled
        assert _url_keys(product) == {"en": "my-own-key", "pl": "duze-krzeslo-sku-1"}

    def test_blank_given_key_is_generated(self, channel_a, feature_set, name_feature, url_key_feature):
        attributes = [_name({"en": "Big Chair"}), {"feature_idx": "url_key", "value_txt_t9n": {"en": "  "}}]

        assert _url_keys(_create("SKU-1", attributes)) == {"en": "big-chair-sku-1"}

    def test_collision_in_the_channel_gets_a_suffix(self, channel_a, feature_set, name_feature, url_key_feature):
        _stored_product(channel_a, "OTHER", None, name_feature, {"en": "big-chair-sku-1"}, url_key_feature)
        _stored_product(channel_a, "OTHER-2", None, name_feature, {"en": "big-chair-sku-1-2"}, url_key_feature)

        product = _create("SKU-1", [_name({"en": "Big Chair"})])

        assert _url_keys(product) == {"en": "big-chair-sku-1-3"}

    def test_other_channel_and_other_language_do_not_collide(
        self, channel_a, channel_b, feature_set, name_feature, url_key_feature
    ):
        _stored_product(channel_b, "OTHER", None, name_feature, {"en": "big-chair-sku-1"}, url_key_feature)
        _stored_product(channel_a, "OTHER-2", None, name_feature, {"pl": "big-chair-sku-1"}, url_key_feature)

        assert _url_keys(_create("SKU-1", [_name({"en": "Big Chair"})])) == {"en": "big-chair-sku-1"}

    def test_no_name_no_key(self, channel_a, feature_set, name_feature, url_key_feature):
        assert _url_keys(_create("SKU-1", [])) == {}

    def test_without_the_system_feature_create_still_works(self, channel_a, feature_set, name_feature):
        product = _create("SKU-1", [_name()])

        assert not ProductAttribute.objects.filter(product=product, feature__idx="url_key").exists()

    def test_through_the_api_the_product_has_a_url_key(
        self, authenticated_client, channel_a, feature_set, name_feature, url_key_feature
    ):
        response = authenticated_client.post(
            "/api/pim/admin/uk-a/products/",
            {"sku": "API-1", "feature_set_idx": "uk-set", "attributes": [_name({"en": "Big Chair"})]},
            format="json",
        )

        assert response.status_code == 201, response.content
        assert response.json()["url_key_t9n"] == {"en": "big-chair-api-1"}


class TestAddToChannel:
    @pytest.fixture
    def source(self, channel_a, feature_set, name_feature, url_key_feature):
        product = _stored_product(
            channel_a, "SRC-1", NAME, name_feature, {"en": "big-chair", "pl": "duze"}, url_key_feature
        )
        product.feature_set = feature_set
        product.save()
        return product

    def test_copy_content_copies_the_url_key(self, source, channel_b):
        new = add_product_to_channel(source, "uk-b", copy_content=True)

        assert _url_keys(new) == {"en": "big-chair", "pl": "duze"}
        assert ProductAttribute.objects.filter(product=new, feature__idx="name").exists()

    def test_collision_in_the_target_channel_gets_a_suffix(self, source, channel_b, name_feature, url_key_feature):
        _stored_product(channel_b, "TAKEN", None, name_feature, {"en": "big-chair"}, url_key_feature)

        new = add_product_to_channel(source, "uk-b", copy_content=True)

        assert _url_keys(new) == {"en": "big-chair-2", "pl": "duze"}
        assert _url_keys(source) == {"en": "big-chair", "pl": "duze"}

    def test_through_the_api(self, authenticated_client, source, channel_b):
        response = authenticated_client.post(
            "/api/pim/admin/uk-a/products/SRC-1/add-to-channel/",
            {"target_channel_idx": "uk-b", "copy_content": True},
            format="json",
        )

        assert response.status_code == 201, response.content
        assert response.json()["url_key_t9n"] == {"en": "big-chair", "pl": "duze"}

    def test_without_copy_content_nothing_is_copied(self, source, channel_b):
        assert _url_keys(add_product_to_channel(source, "uk-b")) == {}

    def test_plain_copy_translations_keeps_the_both_sides_guard(self, source, channel_b, feature_set):
        """A target that carries no system feature of its own does not get them from copy_translations."""
        target = ProductFactory(shop=channel_b, real_product=source.real_product, feature_set=feature_set)

        copy_translations(source, target)

        assert _url_keys(target) == {}
        assert not ProductAttribute.objects.filter(product=target, feature__idx="name").exists()


class TestFillCommand:
    @pytest.fixture
    def products(self, channel_a, channel_b, name_feature, url_key_feature):
        return {
            "bare": _stored_product(channel_a, "BARE-1", {"en": "Big Chair"}, name_feature),
            "given": _stored_product(
                channel_a, "GIVEN-1", {"en": "Big Chair"}, name_feature, {"en": "kept"}, url_key_feature
            ),
            "partial": _stored_product(
                channel_a,
                "PART-1",
                {"en": "Big Chair", "pl": "Krzeslo"},
                name_feature,
                {"en": "kept-2"},
                url_key_feature,
            ),
            "nameless": _stored_product(channel_a, "NONE-1", None, name_feature),
            "other": _stored_product(channel_b, "BARE-2", {"en": "Big Chair"}, name_feature),
        }

    def _run(self, *args: str) -> str:
        out = StringIO()
        call_command("pim_fill_url_keys", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_prints_and_writes_nothing(self, products):
        output = self._run()

        assert "uk-a\tBARE-1\ten\tbig-chair-bare-1" in output
        assert "Would set 3 url_key value(s) on 3 product(s)." in output
        assert ProductAttribute.objects.filter(feature__idx="url_key").count() == 2

    def test_apply_writes_and_never_overwrites(self, products):
        output = self._run("--apply")

        assert "Set 3 url_key value(s) on 3 product(s)." in output
        assert _url_keys(products["bare"]) == {"en": "big-chair-bare-1"}
        assert _url_keys(products["given"]) == {"en": "kept"}
        assert _url_keys(products["partial"]) == {"en": "kept-2", "pl": "krzeslo-part-1"}
        assert _url_keys(products["nameless"]) == {}
        assert _url_keys(products["other"]) == {"en": "big-chair-bare-2"}

    def test_second_apply_is_a_no_op(self, products):
        self._run("--apply")

        assert "Set 0 url_key value(s) on 0 product(s)." in self._run("--apply")

    def test_channel_filter(self, products):
        self._run("--apply", "--channel", "uk-b")

        assert _url_keys(products["other"]) == {"en": "big-chair-bare-2"}
        assert _url_keys(products["bare"]) == {}

    def test_unknown_channel_is_an_error(self, products):
        with pytest.raises(CommandError):
            self._run("--channel", "nope")

    def test_collision_gets_a_suffix(self, channel_a, name_feature, url_key_feature):
        _stored_product(channel_a, "HOLDER", None, name_feature, {"en": "big-chair-bare-1"}, url_key_feature)
        bare = _stored_product(channel_a, "BARE-1", {"en": "Big Chair"}, name_feature)

        self._run("--apply")

        assert _url_keys(bare) == {"en": "big-chair-bare-1-2"}
