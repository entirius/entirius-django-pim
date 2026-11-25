# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# ruff: noqa: F401, F811

"""url_key never duplicates inside a channel: given keys are refused, derived keys are suffixed, writes are locked."""

import threading
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection

from django_pim.exceptions import InvalidRequestError
from django_pim.models import Product, ProductAttribute
from django_pim.services import inheritance_service, product_service, url_key_service
from django_pim.services.inheritance_service import (
    add_product_to_channel,
    copy_translations,
    propagate_to_inheriting_products,
    toggle_language_override,
)
from tests.factories import ChannelFactory, FeatureFactory, FeatureSetFactory, ProductFactory, RealProductFactory
from tests.test_product_url_key import (
    NAME,
    _create,
    _name,
    _stored_product,
    _url_keys,
    channel_a,
    channel_b,
    feature_set,
    name_feature,
    url_key_feature,
)

pytestmark = pytest.mark.django_db


def _update(sku: str, attributes: list[dict], channel_idx: str = "uk-a") -> Product:
    return product_service.update_product(channel_idx, sku, attributes=attributes)


def _key(value: dict) -> list[dict]:
    return [{"feature_idx": "url_key", "value_txt_t9n": value}]


class TestGivenKeysAreRefused:
    def test_create_with_a_taken_key_names_language_and_sku(
        self, channel_a, feature_set, name_feature, url_key_feature
    ):
        _stored_product(channel_a, "HOLDER", None, name_feature, {"pl": "zajety"}, url_key_feature)

        with pytest.raises(InvalidRequestError) as error:
            _create("NEW-1", _key({"en": "free", "pl": "zajety"}))

        assert "(pl)" in error.value.client_message
        assert "'HOLDER'" in error.value.client_message
        assert not Product.objects.filter(real_product__sku="NEW-1").exists()

    def test_create_through_the_api_is_a_400_in_the_v2_format(
        self, authenticated_client, channel_a, feature_set, name_feature, url_key_feature
    ):
        _stored_product(channel_a, "HOLDER", None, name_feature, {"en": "taken"}, url_key_feature)

        response = authenticated_client.post(
            "/api/pim/admin/uk-a/products/",
            {"sku": "NEW-2", "feature_set_idx": "uk-set", "attributes": _key({"en": "taken"})},
            format="json",
        )

        assert response.status_code == 400, response.content
        body = response.json()
        assert body["error"] == "VALIDATION_ERROR"
        assert "HOLDER" in body["message"] or "HOLDER" in str(body["details"])

    def test_a_disabled_hidden_product_still_holds_its_key(self, channel_a, feature_set, name_feature, url_key_feature):
        hidden = _stored_product(channel_a, "HIDDEN", None, name_feature, {"en": "big-chair-new-3"}, url_key_feature)
        Product.objects.filter(pk=hidden.pk).update(is_enabled=False, visibility=0)

        assert _url_keys(_create("NEW-3", [_name({"en": "Big Chair"})])) == {"en": "big-chair-new-3-2"}
        with pytest.raises(InvalidRequestError):
            _create("NEW-4", _key({"en": "big-chair-new-3"}))

    def test_update_to_a_taken_key_is_refused_and_keeps_the_old_one(
        self, channel_a, feature_set, name_feature, url_key_feature
    ):
        _stored_product(channel_a, "HOLDER", None, name_feature, {"en": "taken"}, url_key_feature)
        _create("MINE", _key({"en": "mine"}))

        with pytest.raises(InvalidRequestError, match="HOLDER"):
            _update("MINE", _key({"en": "taken"}))

        assert _url_keys(Product.objects.get(real_product__sku="MINE")) == {"en": "mine"}

    def test_update_to_a_free_key_and_to_its_own_key_works(self, channel_a, feature_set, name_feature, url_key_feature):
        product = _create("MINE", _key({"en": "mine"}))

        _update("MINE", _key({"en": "mine"}))
        _update("MINE", _key({"en": "renamed"}))

        assert _url_keys(product) == {"en": "renamed"}

    def test_an_old_duplicate_does_not_block_an_unrelated_edit(
        self, channel_a, feature_set, name_feature, url_key_feature
    ):
        _stored_product(channel_a, "OLD-1", None, name_feature, {"en": "dup"}, url_key_feature)
        _stored_product(channel_a, "OLD-2", None, name_feature, {"en": "dup"}, url_key_feature)

        _update("OLD-2", _key({"en": "dup"}) + [_name({"en": "New name"})])

        assert _url_keys(Product.objects.get(real_product__sku="OLD-2")) == {"en": "dup"}

    def test_a_blank_key_is_missing_not_a_clash(self, channel_a, feature_set, name_feature, url_key_feature):
        _stored_product(channel_a, "BLANK", None, name_feature, {"en": " "}, url_key_feature)

        product = _create("NEW-5", _key({"en": " "}) + [_name({"en": "Big Chair"})])

        assert _url_keys(product) == {"en": "big-chair-new-5"}


class TestNameChangeKeepsTheUrl:
    def test_update_name_does_not_regenerate_the_key(self, channel_a, feature_set, name_feature, url_key_feature):
        product = _create("STABLE", [_name({"en": "Big Chair"})])

        _update("STABLE", [_name({"en": "Another Name"})])

        assert _url_keys(product) == {"en": "big-chair-stable"}

    def test_update_does_not_generate_a_missing_key(self, channel_a, feature_set, name_feature, url_key_feature):
        product = _stored_product(channel_a, "NOKEY", {"en": "Big Chair"}, name_feature)
        product.feature_set = feature_set
        product.save()

        _update("NOKEY", [_name({"en": "Other"})])

        assert _url_keys(product) == {}


@pytest.fixture
def family(db, name_feature, url_key_feature, feature_set):
    """A default channel and an inheriting child, each with a product of the same SKU carrying a url_key row."""
    default = ChannelFactory(idx="uk-default", is_default=True, inheritance_enabled=True)
    child = ChannelFactory(idx="uk-child", inheritance_enabled=True)
    real = RealProductFactory(sku="FAM-1")
    source = ProductFactory(shop=default, real_product=real, feature_set=feature_set)
    ProductAttribute.objects.create(product=source, feature=name_feature, value_txt_t9n=NAME)
    ProductAttribute.objects.create(product=source, feature=url_key_feature, value_txt_t9n={"en": "shared"})
    target = ProductFactory(shop=child, real_product=real, feature_set=feature_set, inherit_attributes=True)
    ProductAttribute.objects.create(product=target, feature=url_key_feature, value_txt_t9n={"en": "old"})
    _stored_product(child, "RIVAL", None, name_feature, {"en": "shared"}, url_key_feature)
    return source, target


def _row(product: Product) -> ProductAttribute:
    return ProductAttribute.objects.get(product=product, feature__idx="url_key")


class TestDerivedKeysAreSuffixed:
    def test_propagation_suffixes_and_keeps_the_language_overridden(self, family):
        source, target = family

        propagate_to_inheriting_products(source)
        propagate_to_inheriting_products(source)

        row = _row(target)
        assert row.value_txt_t9n == {"en": "shared-2"}
        assert row.overridden_langs == ["en"]

    def test_propagation_without_a_clash_keeps_following_the_default(self, family):
        source, target = family
        Product.objects.filter(real_product__sku="RIVAL").delete()

        propagate_to_inheriting_products(source)

        row = _row(target)
        assert (row.value_txt_t9n, row.overridden_langs) == ({"en": "shared"}, [])

    def test_toggle_back_to_inherited_suffixes_a_taken_key(self, family):
        source, target = family

        attr = toggle_language_override(target, "url_key", "en", override=False)

        assert attr.value_txt_t9n == {"en": "shared-2"}
        assert attr.overridden_langs == ["en"]

    def test_standalone_copy_translations_suffixes(self, family):
        source, target = family

        copy_translations(source, target)

        assert _row(target).value_txt_t9n == {"en": "shared-2"}

    def test_add_to_channel_copy_suffixes(self, family, channel_b):
        source, _target = family
        _stored_product(
            channel_b, "OTHER", None, source.products_attributes.first().feature, {"en": "shared"}, _row(source).feature
        )

        new = add_product_to_channel(source, "uk-b", copy_content=True)

        assert _url_keys(new) == {"en": "shared-2"}


class TestLength:
    def test_a_suffixed_key_stays_within_the_limit(self, channel_a, feature_set, name_feature, url_key_feature):
        base = "a" * url_key_service.URL_KEY_MAX_LENGTH
        _stored_product(channel_a, "LONG", None, name_feature, {"en": base}, url_key_feature)

        key = url_key_service.unique_url_key(channel_a, "en", base)

        assert len(key) == url_key_service.URL_KEY_MAX_LENGTH
        assert key.endswith("-2")

    def test_copied_key_at_the_limit_is_trimmed_before_the_suffix(
        self, channel_a, channel_b, feature_set, name_feature, url_key_feature
    ):
        base = "b" * url_key_service.URL_KEY_MAX_LENGTH
        source = _stored_product(channel_a, "SRC", NAME, name_feature, {"en": base}, url_key_feature)
        source.feature_set = feature_set
        source.save()
        _stored_product(channel_b, "TAKEN", None, name_feature, {"en": base}, url_key_feature)

        new = add_product_to_channel(source, "uk-b", copy_content=True)

        assert _url_keys(new)["en"] == "b" * (url_key_service.URL_KEY_MAX_LENGTH - 2) + "-2"


class TestFillCommandPreviewAndReport:
    @pytest.fixture
    def twins(self, channel_a, name_feature, url_key_feature):
        """Two SKUs that slug to the same key."""
        _stored_product(channel_a, "RACE/1", {"en": "Chair"}, name_feature)
        _stored_product(channel_a, "RACE-1", {"en": "Chair"}, name_feature)

    def _run(self, *args: str) -> list[str]:
        out = StringIO()
        call_command("pim_fill_url_keys", *args, stdout=out)
        return [line for line in out.getvalue().splitlines() if line.startswith("uk-a")]

    def test_dry_run_reserves_its_keys_so_preview_equals_apply(self, twins):
        preview = self._run()
        applied = self._run("--apply")

        assert preview == applied
        assert sorted(line.split("\t")[3] for line in applied) == ["chair-race-1", "chair-race-1-2"]

    def test_duplicates_are_listed_never_rewritten(self, channel_a, name_feature, url_key_feature):
        _stored_product(channel_a, "DUP-1", None, name_feature, {"en": "same", "pl": "inny"}, url_key_feature)
        _stored_product(channel_a, "DUP-2", None, name_feature, {"en": "same"}, url_key_feature)
        out = StringIO()

        call_command("pim_fill_url_keys", "--apply", stdout=out)

        assert "DUPLICATE\tuk-a\ten\tsame\tDUP-1, DUP-2" in out.getvalue()
        assert "already stored: 1 (listed only, none changed)" in out.getvalue()
        assert [_url_keys(p) for p in Product.objects.order_by("pk")][0] == {"en": "same", "pl": "inny"}


class TestLocks:
    @pytest.fixture
    def locked(self):
        real = url_key_service.lock_url_keys
        with (
            patch.object(url_key_service, "lock_url_keys", wraps=real) as lock,
            patch.object(inheritance_service, "lock_url_keys", wraps=real),
        ):
            yield lock

    def test_create_locks_its_channel(self, locked, channel_a, feature_set, name_feature, url_key_feature):
        _create("LOCK-1", [_name({"en": "Chair"})])

        locked.assert_called_once_with(channel_a)

    def test_update_with_a_url_key_locks_its_channel(
        self, locked, channel_a, feature_set, name_feature, url_key_feature
    ):
        _create("LOCK-2", [_name({"en": "Chair"})])
        locked.reset_mock()

        _update("LOCK-2", _key({"en": "changed"}))

        assert [c.args[0].pk for c in locked.call_args_list] == [channel_a.pk]

    def test_add_to_channel_locks_the_target(self, locked, family, channel_b):
        source, _target = family

        add_product_to_channel(source, "uk-b", copy_content=True)

        assert {c.args[0].idx for c in locked.call_args_list} == {"uk-b"}

    def test_propagation_and_copy_lock_the_child(self, locked, family):
        source, target = family

        propagate_to_inheriting_products(source)
        copy_translations(source, target)

        assert {c.args[0].idx for c in locked.call_args_list} == {"uk-child"}

    def test_fill_apply_locks_each_channel_dry_run_does_not(self, locked, channel_a, name_feature, url_key_feature):
        _stored_product(channel_a, "LOCK-3", {"en": "Chair"}, name_feature)

        call_command("pim_fill_url_keys", stdout=StringIO())
        assert locked.call_count == 0
        call_command("pim_fill_url_keys", "--apply", stdout=StringIO())

        assert locked.call_count == 1


@pytest.mark.django_db(transaction=True)
class TestRace:
    def test_two_concurrent_creates_get_two_different_keys(self, channel_a, feature_set, name_feature, url_key_feature):
        """Both threads finish their uniqueness check at the same moment; the channel lock must still keep them apart.

        Without the lock both see the key as free and both write it. With it the second one waits until the
        first commits (the barrier then times out for the one that holds the lock) and picks the next suffix.
        """
        barrier = threading.Barrier(2)
        real_check = url_key_service._is_taken
        errors: list[Exception] = []

        def check_then_wait(*args, **kwargs):
            taken = real_check(*args, **kwargs)
            try:
                barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
            return taken

        def worker(sku: str) -> None:
            try:
                _create(sku, [_name({"en": "Chair"})])
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        with patch.object(url_key_service, "_is_taken", check_then_wait):
            threads = [threading.Thread(target=worker, args=(sku,)) for sku in ("RACE/1", "RACE-1")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

        assert not errors
        keys = sorted(row.value_txt_t9n["en"] for row in ProductAttribute.objects.filter(feature__idx="url_key"))
        assert keys == ["chair-race-1", "chair-race-1-2"]
