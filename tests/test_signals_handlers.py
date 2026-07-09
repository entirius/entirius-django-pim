# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for Phase 6B: Signal-Driven PIM → Matrix sync.

Tests verify that signal handlers call enqueue_product_sync with correct
arguments and honour all skip conditions (raw, suppressed, disabled, denylist).
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import TestCase

from django_pim.models import (
    Attribute,
    Feature,
    FeatureInFeatureSet,
    Product,
    ProductAttribute,
    ProductInCategory,
    ProductPicture,
    ProductVideo,
    RealProduct,
)
from django_pim.models.pim_settings import PimSettings
from django_pim.signals.killswitch import suppress_matrix_signals

ENQUEUE_PATH = "django_pim.signals.handlers.enqueue_product_sync"


def _enable_signals() -> None:
    """Enable matrix signals and clear the 60-second cache."""
    settings = PimSettings.load()
    settings.matrix_signals_enabled = True
    settings.save()
    cache.delete("pim:matrix_signals_enabled")


def _disable_signals() -> None:
    settings = PimSettings.load()
    settings.matrix_signals_enabled = False
    settings.save()
    cache.delete("pim:matrix_signals_enabled")


# ─── Product ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProductPostSaveSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_create_calls_enqueue_with_sku_and_channel(self, mock_enqueue):
        from tests.factories import ProductFactory

        product = ProductFactory()

        mock_enqueue.assert_called_once_with(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_update_calls_enqueue(self, mock_enqueue):
        from tests.factories import ProductFactory

        product = ProductFactory()
        mock_enqueue.reset_mock()

        product.is_enabled = not product.is_enabled
        product.save()

        mock_enqueue.assert_called_once_with(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_raw_true_skips_enqueue(self, mock_enqueue):
        """Fixture loads (raw=True) must not trigger sync."""
        from django_pim.signals.handlers import product_post_save

        mock_instance = MagicMock()
        mock_instance.real_product.sku = "RAW-SKU-001"
        mock_instance.shop.idx = "test-channel"

        product_post_save(sender=Product, instance=mock_instance, created=True, raw=True)

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_skips_when_suppressed(self, mock_enqueue):
        from tests.factories import ProductFactory

        with suppress_matrix_signals():
            ProductFactory()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_skips_when_signals_disabled(self, mock_enqueue):
        _disable_signals()

        from tests.factories import ProductFactory

        ProductFactory()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_skips_when_channel_in_denylist(self, mock_enqueue):
        from django_pim import settings as pim_settings
        from tests.factories import ChannelFactory, FeatureSetFactory, ProductFactory, RealProductFactory

        channel = ChannelFactory(idx="denylist-channel-1")
        product = ProductFactory(shop=channel, real_product=RealProductFactory(), feature_set=FeatureSetFactory())
        mock_enqueue.reset_mock()

        original = pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST
        pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST = ["denylist-channel-1"]
        try:
            product.is_enabled = not product.is_enabled
            product.save()
            mock_enqueue.assert_not_called()
        finally:
            pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST = original


@pytest.mark.django_db
class TestProductPostDeleteSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_delete_calls_enqueue_with_sku_and_channel(self, mock_enqueue):
        from tests.factories import ProductFactory

        product = ProductFactory()
        sku = product.real_product.sku
        channel_idx = product.shop.idx
        mock_enqueue.reset_mock()

        product.delete()

        mock_enqueue.assert_called_once_with(sku, channel_idx)

    @patch(ENQUEUE_PATH)
    def test_delete_skips_when_suppressed(self, mock_enqueue):
        from tests.factories import ProductFactory

        product = ProductFactory()
        mock_enqueue.reset_mock()

        with suppress_matrix_signals():
            product.delete()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_delete_skips_when_signals_disabled(self, mock_enqueue):
        from tests.factories import ProductFactory

        product = ProductFactory()
        mock_enqueue.reset_mock()
        _disable_signals()

        product.delete()

        mock_enqueue.assert_not_called()


# ─── ProductAttribute ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProductAttributeSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_post_save_enqueues_parent_product(self, mock_enqueue):
        from tests.factories import FeatureFactory, ProductFactory

        product = ProductFactory()
        feature = FeatureFactory(feature_type=1)  # BOOL
        mock_enqueue.reset_mock()

        ProductAttribute.objects.create(product=product, feature=feature, value_bool=True)

        mock_enqueue.assert_called_once_with(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_post_delete_enqueues_parent_product(self, mock_enqueue):
        from tests.factories import FeatureFactory, ProductFactory

        product = ProductFactory()
        feature = FeatureFactory(feature_type=1)  # BOOL
        pa = ProductAttribute.objects.create(product=product, feature=feature, value_bool=True)
        mock_enqueue.reset_mock()

        pa.delete()

        mock_enqueue.assert_called_once_with(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_post_save_skips_when_suppressed(self, mock_enqueue):
        from tests.factories import FeatureFactory, ProductFactory

        product = ProductFactory()
        feature = FeatureFactory(feature_type=1)  # BOOL
        mock_enqueue.reset_mock()

        with suppress_matrix_signals():
            ProductAttribute.objects.create(product=product, feature=feature, value_bool=True)

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_post_save_raw_skips_enqueue(self, mock_enqueue):
        from django_pim.signals.handlers import product_attribute_post_save

        mock_instance = MagicMock()

        product_attribute_post_save(sender=ProductAttribute, instance=mock_instance, created=True, raw=True)

        mock_enqueue.assert_not_called()


# ─── RealProduct ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRealProductPostSaveSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_fans_out_to_all_linked_channels(self, mock_enqueue):
        from tests.factories import ChannelFactory, FeatureSetFactory, ProductFactory, RealProductFactory

        real_product = RealProductFactory()
        ch_a = ChannelFactory(idx="fanout-ch-a", name="Fanout Ch A")
        ch_b = ChannelFactory(idx="fanout-ch-b", name="Fanout Ch B")
        ch_c = ChannelFactory(idx="fanout-ch-c", name="Fanout Ch C")
        fs = FeatureSetFactory()

        ProductFactory(real_product=real_product, shop=ch_a, feature_set=fs)
        ProductFactory(real_product=real_product, shop=ch_b, feature_set=fs)
        ProductFactory(real_product=real_product, shop=ch_c, feature_set=fs)
        mock_enqueue.reset_mock()

        real_product.weight = 999
        real_product.save()

        assert mock_enqueue.call_count == 3
        called_channels = {call[0][1] for call in mock_enqueue.call_args_list}
        assert called_channels == {"fanout-ch-a", "fanout-ch-b", "fanout-ch-c"}

    @patch(ENQUEUE_PATH)
    def test_no_linked_products_means_no_enqueue(self, mock_enqueue):
        from tests.factories import RealProductFactory

        real_product = RealProductFactory()
        mock_enqueue.reset_mock()

        real_product.weight = 500
        real_product.save()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_skips_when_suppressed(self, mock_enqueue):
        from tests.factories import ChannelFactory, FeatureSetFactory, ProductFactory, RealProductFactory

        real_product = RealProductFactory()
        ch = ChannelFactory(idx="suppress-rp-ch")
        ProductFactory(real_product=real_product, shop=ch, feature_set=FeatureSetFactory())
        mock_enqueue.reset_mock()

        with suppress_matrix_signals():
            real_product.weight = 100
            real_product.save()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_raw_true_skips_enqueue(self, mock_enqueue):
        from django_pim.signals.handlers import real_product_post_save

        mock_instance = MagicMock()

        real_product_post_save(sender=RealProduct, instance=mock_instance, created=False, raw=True)

        mock_enqueue.assert_not_called()


# ─── Attribute (cascade) ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAttributeCascadeSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_cascades_to_products_using_attribute(self, mock_enqueue):
        from tests.factories import AttributeFactory, FeatureFactory, ProductFactory

        feature = FeatureFactory(feature_type=7)  # SELECT
        attribute = AttributeFactory(feature=feature)
        product = ProductFactory()
        FeatureInFeatureSet.objects.create(feature=feature, feature_set=product.feature_set, position=1)
        ProductAttribute.objects.create(product=product, feature=feature, attribute=attribute)
        mock_enqueue.reset_mock()

        attribute.display_order = 99
        attribute.save()

        mock_enqueue.assert_any_call(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_attribute_with_no_linked_products_does_not_enqueue(self, mock_enqueue):
        from tests.factories import AttributeFactory, FeatureFactory

        feature = FeatureFactory(feature_type=7)  # SELECT
        attribute = AttributeFactory(feature=feature)
        mock_enqueue.reset_mock()

        attribute.display_order = 50
        attribute.save()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_skips_when_suppressed(self, mock_enqueue):
        from tests.factories import AttributeFactory, FeatureFactory, ProductFactory

        feature = FeatureFactory(feature_type=7)  # SELECT
        attribute = AttributeFactory(feature=feature)
        product = ProductFactory()
        FeatureInFeatureSet.objects.create(feature=feature, feature_set=product.feature_set, position=1)
        ProductAttribute.objects.create(product=product, feature=feature, attribute=attribute)
        mock_enqueue.reset_mock()

        with suppress_matrix_signals():
            attribute.display_order = 10
            attribute.save()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_raw_true_skips_enqueue(self, mock_enqueue):
        from django_pim.signals.handlers import attribute_post_save

        mock_instance = MagicMock()

        attribute_post_save(sender=Attribute, instance=mock_instance, created=False, raw=True)

        mock_enqueue.assert_not_called()


# ─── Feature (cascade) ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestFeatureCascadeSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_cascades_via_feature_set_to_products(self, mock_enqueue):
        from tests.factories import FeatureFactory, FeatureSetFactory, ProductFactory

        feature = FeatureFactory()
        feature_set = FeatureSetFactory()
        FeatureInFeatureSet.objects.create(feature=feature, feature_set=feature_set, position=1)
        product = ProductFactory(feature_set=feature_set)
        mock_enqueue.reset_mock()

        feature.save()

        mock_enqueue.assert_any_call(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_feature_not_in_any_set_does_not_enqueue(self, mock_enqueue):
        from tests.factories import FeatureFactory

        feature = FeatureFactory()
        mock_enqueue.reset_mock()

        feature.save()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_skips_when_suppressed(self, mock_enqueue):
        from tests.factories import FeatureFactory, FeatureSetFactory, ProductFactory

        feature = FeatureFactory()
        feature_set = FeatureSetFactory()
        FeatureInFeatureSet.objects.create(feature=feature, feature_set=feature_set, position=1)
        ProductFactory(feature_set=feature_set)
        mock_enqueue.reset_mock()

        with suppress_matrix_signals():
            feature.save()

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_raw_true_skips_enqueue(self, mock_enqueue):
        from django_pim.signals.handlers import feature_post_save

        mock_instance = MagicMock()

        feature_post_save(sender=Feature, instance=mock_instance, created=False, raw=True)

        mock_enqueue.assert_not_called()


# ─── ProductPicture ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProductPictureSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_post_save_enqueues_product(self, mock_enqueue):
        """Invoke handler directly with a mocked ProductPicture instance."""
        from django_pim.signals.handlers import product_picture_post_save

        mock_product = MagicMock()
        mock_product.real_product.sku = "PIC-SKU-001"
        mock_product.shop.idx = "test-channel"

        mock_pp = MagicMock(spec=ProductPicture)
        mock_pp.product = mock_product

        product_picture_post_save(sender=ProductPicture, instance=mock_pp, created=True, raw=False)

        mock_enqueue.assert_called_once_with("PIC-SKU-001", "test-channel")

    @patch(ENQUEUE_PATH)
    def test_post_delete_enqueues_product(self, mock_enqueue):
        from django_pim.signals.handlers import product_picture_post_delete

        mock_product = MagicMock()
        mock_product.real_product.sku = "PIC-SKU-002"
        mock_product.shop.idx = "test-channel"

        mock_pp = MagicMock(spec=ProductPicture)
        mock_pp.product = mock_product

        product_picture_post_delete(sender=ProductPicture, instance=mock_pp)

        mock_enqueue.assert_called_once_with("PIC-SKU-002", "test-channel")

    @patch(ENQUEUE_PATH)
    def test_post_save_raw_skips_enqueue(self, mock_enqueue):
        from django_pim.signals.handlers import product_picture_post_save

        mock_pp = MagicMock(spec=ProductPicture)

        product_picture_post_save(sender=ProductPicture, instance=mock_pp, created=True, raw=True)

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_post_save_skips_when_suppressed(self, mock_enqueue):
        from django_pim.signals.handlers import product_picture_post_save

        mock_product = MagicMock()
        mock_product.real_product.sku = "PIC-SUPP-001"
        mock_product.shop.idx = "test-channel"
        mock_pp = MagicMock(spec=ProductPicture)
        mock_pp.product = mock_product

        with suppress_matrix_signals():
            product_picture_post_save(sender=ProductPicture, instance=mock_pp, created=True, raw=False)

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_post_delete_skips_when_suppressed(self, mock_enqueue):
        from django_pim.signals.handlers import product_picture_post_delete

        mock_product = MagicMock()
        mock_product.real_product.sku = "PIC-SUPP-002"
        mock_product.shop.idx = "test-channel"
        mock_pp = MagicMock(spec=ProductPicture)
        mock_pp.product = mock_product

        with suppress_matrix_signals():
            product_picture_post_delete(sender=ProductPicture, instance=mock_pp)

        mock_enqueue.assert_not_called()


# ─── ProductVideo ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProductVideoSignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_post_save_enqueues_product(self, mock_enqueue):
        from django_pim.signals.handlers import product_video_post_save

        mock_product = MagicMock()
        mock_product.real_product.sku = "VID-SKU-001"
        mock_product.shop.idx = "test-channel"

        mock_pv = MagicMock(spec=ProductVideo)
        mock_pv.product = mock_product

        product_video_post_save(sender=ProductVideo, instance=mock_pv, created=True, raw=False)

        mock_enqueue.assert_called_once_with("VID-SKU-001", "test-channel")

    @patch(ENQUEUE_PATH)
    def test_post_delete_enqueues_product(self, mock_enqueue):
        from django_pim.signals.handlers import product_video_post_delete

        mock_product = MagicMock()
        mock_product.real_product.sku = "VID-SKU-002"
        mock_product.shop.idx = "test-channel"

        mock_pv = MagicMock(spec=ProductVideo)
        mock_pv.product = mock_product

        product_video_post_delete(sender=ProductVideo, instance=mock_pv)

        mock_enqueue.assert_called_once_with("VID-SKU-002", "test-channel")

    @patch(ENQUEUE_PATH)
    def test_post_save_raw_skips_enqueue(self, mock_enqueue):
        from django_pim.signals.handlers import product_video_post_save

        mock_pv = MagicMock(spec=ProductVideo)

        product_video_post_save(sender=ProductVideo, instance=mock_pv, created=True, raw=True)

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_post_save_skips_when_suppressed(self, mock_enqueue):
        from django_pim.signals.handlers import product_video_post_save

        mock_product = MagicMock()
        mock_product.real_product.sku = "VID-SUPP-001"
        mock_product.shop.idx = "test-channel"
        mock_pv = MagicMock(spec=ProductVideo)
        mock_pv.product = mock_product

        with suppress_matrix_signals():
            product_video_post_save(sender=ProductVideo, instance=mock_pv, created=True, raw=False)

        mock_enqueue.assert_not_called()


# ─── ProductInCategory ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProductInCategorySignal(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_post_save_enqueues_product(self, mock_enqueue):
        from tests.factories import ProductCategoryFactory, ProductFactory

        product = ProductFactory()
        category = ProductCategoryFactory(shop=product.shop)
        mock_enqueue.reset_mock()

        ProductInCategory.objects.create(product=product, category=category)

        mock_enqueue.assert_called_once_with(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_post_delete_enqueues_product(self, mock_enqueue):
        from tests.factories import ProductCategoryFactory, ProductFactory

        product = ProductFactory()
        category = ProductCategoryFactory(shop=product.shop)
        pic = ProductInCategory.objects.create(product=product, category=category)
        mock_enqueue.reset_mock()

        pic.delete()

        mock_enqueue.assert_called_once_with(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_post_save_skips_when_suppressed(self, mock_enqueue):
        from tests.factories import ProductCategoryFactory, ProductFactory

        product = ProductFactory()
        category = ProductCategoryFactory(shop=product.shop)
        mock_enqueue.reset_mock()

        with suppress_matrix_signals():
            ProductInCategory.objects.create(product=product, category=category)

        mock_enqueue.assert_not_called()

    @patch(ENQUEUE_PATH)
    def test_post_save_raw_skips_enqueue(self, mock_enqueue):
        from django_pim.signals.handlers import product_in_category_post_save

        mock_instance = MagicMock()

        product_in_category_post_save(sender=ProductInCategory, instance=mock_instance, created=True, raw=True)

        mock_enqueue.assert_not_called()


# ─── Batch threshold ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCascadeBatchThreshold(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_attribute_cascade_below_threshold_enqueues_per_product(self, mock_enqueue):
        from django_pim import settings as pim_settings
        from tests.factories import AttributeFactory, FeatureFactory, FeatureSetFactory, ProductFactory

        original = pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD
        pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = 100

        try:
            feature = FeatureFactory(feature_type=7)  # SELECT
            attribute = AttributeFactory(feature=feature)
            fs = FeatureSetFactory()
            FeatureInFeatureSet.objects.create(feature=feature, feature_set=fs, position=1)
            products = [ProductFactory(feature_set=fs) for _ in range(3)]
            for p in products:
                ProductAttribute.objects.create(product=p, feature=feature, attribute=attribute)
            mock_enqueue.reset_mock()

            attribute.display_order = 42
            attribute.save()

            assert mock_enqueue.call_count == 3
        finally:
            pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = original

    @patch(ENQUEUE_PATH)
    def test_attribute_cascade_above_threshold_enqueues_channel_rebuild(self, mock_enqueue):
        from django_pim import settings as pim_settings
        from tests.factories import (
            AttributeFactory,
            ChannelFactory,
            FeatureFactory,
            FeatureSetFactory,
            ProductFactory,
            RealProductFactory,
        )

        original = pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD
        pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = 2

        try:
            channel = ChannelFactory(idx="threshold-ch-1", name="Threshold Ch 1")
            fs = FeatureSetFactory()
            feature = FeatureFactory(feature_type=7)  # SELECT
            attribute = AttributeFactory(feature=feature)
            FeatureInFeatureSet.objects.create(feature=feature, feature_set=fs, position=1)
            for _ in range(5):
                p = ProductFactory(shop=channel, feature_set=fs, real_product=RealProductFactory())
                ProductAttribute.objects.create(product=p, feature=feature, attribute=attribute)
            mock_enqueue.reset_mock()

            attribute.display_order = 77
            attribute.save()

            rebuild_calls = [c for c in mock_enqueue.call_args_list if c[0][0] == "__CHANNEL_REBUILD__"]
            assert len(rebuild_calls) >= 1
            rebuild_channels = {c[0][1] for c in rebuild_calls}
            assert "threshold-ch-1" in rebuild_channels
        finally:
            pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = original

    @patch(ENQUEUE_PATH)
    def test_feature_cascade_above_threshold_enqueues_channel_rebuild(self, mock_enqueue):
        from django_pim import settings as pim_settings
        from tests.factories import (
            ChannelFactory,
            FeatureFactory,
            FeatureSetFactory,
            ProductFactory,
            RealProductFactory,
        )

        original = pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD
        pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = 2

        try:
            channel = ChannelFactory(idx="threshold-ch-2", name="Threshold Ch 2")
            feature = FeatureFactory(feature_type=7)  # SELECT
            feature_set = FeatureSetFactory()
            FeatureInFeatureSet.objects.create(feature=feature, feature_set=feature_set, position=1)
            for _ in range(5):
                ProductFactory(shop=channel, feature_set=feature_set, real_product=RealProductFactory())
            mock_enqueue.reset_mock()

            feature.save()

            rebuild_calls = [c for c in mock_enqueue.call_args_list if c[0][0] == "__CHANNEL_REBUILD__"]
            assert len(rebuild_calls) >= 1
        finally:
            pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = original

    @patch(ENQUEUE_PATH)
    def test_channel_rebuild_respects_denylist(self, mock_enqueue):
        """Channels in denylist are excluded from __CHANNEL_REBUILD__ calls."""
        from django_pim import settings as pim_settings
        from tests.factories import (
            AttributeFactory,
            ChannelFactory,
            FeatureFactory,
            FeatureSetFactory,
            ProductFactory,
            RealProductFactory,
        )

        original_threshold = pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD
        original_denylist = pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST
        pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = 2

        try:
            channel = ChannelFactory(idx="deny-rebuild-ch", name="Deny Rebuild Ch")
            fs = FeatureSetFactory()
            feature = FeatureFactory(feature_type=7)  # SELECT
            attribute = AttributeFactory(feature=feature)
            FeatureInFeatureSet.objects.create(feature=feature, feature_set=fs, position=1)
            for _ in range(5):
                p = ProductFactory(shop=channel, feature_set=fs, real_product=RealProductFactory())
                ProductAttribute.objects.create(product=p, feature=feature, attribute=attribute)
            mock_enqueue.reset_mock()

            pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST = ["deny-rebuild-ch"]
            attribute.display_order = 1
            attribute.save()

            rebuild_calls = [
                c
                for c in mock_enqueue.call_args_list
                if c[0][0] == "__CHANNEL_REBUILD__" and c[0][1] == "deny-rebuild-ch"
            ]
            assert len(rebuild_calls) == 0
        finally:
            pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = original_threshold
            pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST = original_denylist


# ─── Edge cases ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSignalEdgeCases(TestCase):
    def setUp(self):
        _enable_signals()

    @patch(ENQUEUE_PATH)
    def test_multiple_saves_each_call_enqueue(self, mock_enqueue):
        """Every save triggers enqueue — debouncing is Redis-side, not in the handler."""
        from tests.factories import ProductFactory

        product = ProductFactory()
        mock_enqueue.reset_mock()

        for i in range(4):
            product.is_enabled = i % 2 == 0
            product.save()

        assert mock_enqueue.call_count == 4

    @patch(ENQUEUE_PATH)
    def test_enqueue_exception_does_not_propagate(self, mock_enqueue):
        """A failure inside enqueue_product_sync must not crash the request."""
        mock_enqueue.side_effect = Exception("Redis down")

        from tests.factories import ProductFactory

        # No exception should escape the signal handler.
        try:
            ProductFactory()
        except Exception as exc:
            self.fail(f"Signal handler propagated an exception: {exc}")

    @patch(ENQUEUE_PATH)
    def test_disabled_then_enabled_resumes_sync(self, mock_enqueue):
        from tests.factories import ProductFactory

        _disable_signals()
        with suppress_matrix_signals():
            ProductFactory()
        mock_enqueue.assert_not_called()

        _enable_signals()
        product = ProductFactory()
        assert mock_enqueue.called
        mock_enqueue.assert_called_with(product.real_product.sku, product.shop.idx)

    @patch(ENQUEUE_PATH)
    def test_suppress_context_manager_restores_on_exception(self, mock_enqueue):
        """suppress_matrix_signals must restore state even if the body raises."""
        from tests.factories import ProductFactory

        try:
            with suppress_matrix_signals():
                raise ValueError("intentional")
        except ValueError:
            pass

        # After context exits (even abnormally), signals should fire again.
        product = ProductFactory()
        mock_enqueue.assert_called_with(product.real_product.sku, product.shop.idx)
