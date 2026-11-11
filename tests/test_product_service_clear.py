# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`product_service.clear_product_attribute`: the one way to drop a stored value (`update_product` cannot)."""

from unittest import mock

import pytest
from django.db.models.signals import post_save

from django_pim.models import FeatureTypeEnum, Product, ProductAttribute
from django_pim.services import product_service

from .factories import (
    ChannelFactory,
    FeatureFactory,
    FeatureSetFactory,
    ProductFactory,
    RealProductFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    channel = ChannelFactory(is_default=True)
    return ProductFactory(shop=channel, real_product=RealProductFactory(sku="CLR-1"), feature_set=FeatureSetFactory())


@pytest.fixture
def product_saved():
    """Collects the instances of every Product `post_save`, as the Matrix sync receives them."""
    received = []

    def receiver(sender, instance, **kwargs):
        received.append(instance.pk)

    post_save.connect(receiver, sender=Product, weak=False)
    yield received
    post_save.disconnect(receiver, sender=Product)


def _store(product, idx, **value):
    feature = FeatureFactory(idx=idx, feature_type=FeatureTypeEnum.DECIMAL)
    return ProductAttribute.objects.create(product=product, feature=feature, **value)


def test_removes_only_the_named_feature(product):
    _store(product, "clr_weight", value_decimal=3)
    kept = _store(product, "clr_other", value_decimal=4)

    result = product_service.clear_product_attribute(product.shop.idx, "CLR-1", "clr_weight")

    assert result.pk == product.pk
    assert list(ProductAttribute.objects.filter(product=product)) == [kept]


def test_fires_the_product_change_signal_once(product, product_saved):
    _store(product, "clr_weight", value_decimal=3)

    product_service.clear_product_attribute(product.shop.idx, "CLR-1", "clr_weight")

    assert product_saved == [product.pk]


def test_nothing_stored_changes_nothing_and_signals_nothing(product, product_saved):
    FeatureFactory(idx="clr_weight", feature_type=FeatureTypeEnum.DECIMAL)

    product_service.clear_product_attribute(product.shop.idx, "CLR-1", "clr_weight")

    assert product_saved == []


def test_unknown_sku_raises(product):
    with pytest.raises(Product.DoesNotExist):
        product_service.clear_product_attribute(product.shop.idx, "NOPE", "clr_weight")


def test_default_channel_clear_is_propagated_to_inheriting_channels(product):
    _store(product, "clr_weight", value_decimal=3)
    child_channel = ChannelFactory(inheritance_enabled=True)
    ProductFactory(
        shop=child_channel,
        real_product=product.real_product,
        feature_set=FeatureSetFactory(),
        inherit_attributes=True,
    )
    product.shop.inheritance_enabled = True
    product.shop.save()

    with mock.patch("django_pim.services.inheritance_service.propagate_to_inheriting_products") as propagate:
        product_service.clear_product_attribute(product.shop.idx, "CLR-1", "clr_weight")

    propagate.assert_called_once()
    assert propagate.call_args.args[1] == ["clr_weight"]
