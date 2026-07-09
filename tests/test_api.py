# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.test import TestCase
from django.urls import reverse

from . import factories


# Create your tests here.
class SetupTestCase(TestCase):
    def test_regional_setup(self):
        language = factories.LanguageFactory()
        currency = factories.CurrencyFactory()

    def test_shop_setup(self):
        shop = factories.ShopFactory()

    def test_feature_set_setup(self):
        f_set = factories.FeatureSetFactory()

    def test_feature_setup(self):
        feature = factories.FeatureFactory()
        feature.features_sets.add(factories.FeatureSetFactory())

    def test_attribute_setup(self):
        feature = factories.FeatureFactory()
        attr = factories.AttributeFactory(feature=feature)

    def test_product_category_setup(self):
        category = factories.ProductCategoryFactory()

    def test_product_setup(self):
        product = factories.ProductFactory()


class FeatureSetApiTestCase(TestCase):
    def setUp(self) -> None:
        self.shop = factories.ShopFactory()
        self.test_instance = factories.FeatureSetFactory()
        return super().setUp()

    def test_list_response(self):
        view_kwargs = {"version": "v1", "shop_idx": self.shop.idx}
        url = reverse("admin-feature-set-list", kwargs=view_kwargs)
        res = self.client.get(url, content_type="application/json")

        data = res.json()

        self.assertTrue("meta" in data)
        self.assertTrue("data" in data)
        self.assertTrue("pagination" in data)
        self.assertTrue(data["data"][0]["idx"] == self.test_instance.idx)
        self.assertTrue(data["data"][0]["name"] == self.test_instance.name)

    def test_details_response(self):
        view_kwargs = {"version": "v1", "shop_idx": self.shop.idx, "idx": self.test_instance.idx}
        url = reverse("admin-feature-set-detail", kwargs=view_kwargs)
        res = self.client.get(url, content_type="application/json")
        data = res.json()

        self.assertTrue("meta" in data)
        self.assertTrue("data" in data)
        self.assertTrue("pagination" not in data)
        self.assertTrue(data["data"]["idx"] == self.test_instance.idx)
        self.assertTrue(data["data"]["name"] == self.test_instance.name)


class FeatureApiTestCase(TestCase):
    def setUp(self) -> None:
        self.shop = factories.ShopFactory()
        self.test_instance = factories.FeatureFactory()
        return super().setUp()

    def test_list_response(self):
        view_kwargs = {"version": "v1", "shop_idx": self.shop.idx}
        url = reverse("admin-feature-list", kwargs=view_kwargs)
        res = self.client.get(url, content_type="application/json")

        data = res.json()

        self.assertTrue("meta" in data)
        self.assertTrue("data" in data)
        self.assertTrue("pagination" in data)
        # The list returns all features for the channel (incl. system features) in an
        # unspecified order — assert presence by idx, not a positional [0] match.
        self.assertIn(self.test_instance.idx, [item["idx"] for item in data["data"]])

    def test_details_response(self):
        view_kwargs = {"version": "v1", "shop_idx": self.shop.idx, "idx": self.test_instance.idx}
        url = reverse("admin-feature-detail", kwargs=view_kwargs)
        res = self.client.get(url, content_type="application/json")
        data = res.json()

        self.assertTrue("meta" in data)
        self.assertTrue("data" in data)
        self.assertTrue("pagination" not in data)
        self.assertTrue(data["data"]["idx"] == self.test_instance.idx)


class ProductCategoryApiTestCase(TestCase):
    def setUp(self) -> None:
        self.test_instance = factories.ProductCategoryFactory()
        self.shop = self.test_instance.shop
        return super().setUp()

    def test_list_response(self):
        view_kwargs = {"version": "v1", "shop_idx": self.shop.idx}
        url = reverse("admin-category-list", kwargs=view_kwargs)
        res = self.client.get(url, content_type="application/json")

        data = res.json()

        self.assertTrue("meta" in data)
        self.assertTrue("data" in data)
        self.assertTrue("pagination" in data)
        self.assertTrue(data["data"][0]["idx"] == self.test_instance.idx)

    def test_details_response(self):
        view_kwargs = {"version": "v1", "shop_idx": self.shop.idx, "idx": self.test_instance.idx}
        url = reverse("admin-category-detail", kwargs=view_kwargs)
        res = self.client.get(url, content_type="application/json")
        data = res.json()

        self.assertTrue("meta" in data)
        self.assertTrue("data" in data)
        self.assertTrue("pagination" not in data)
        self.assertTrue(data["data"]["idx"] == self.test_instance.idx)
