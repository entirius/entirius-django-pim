# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A cleared DECIMAL attribute (null, "" or blanks) is "no value"; garbage is a 400, never a 500."""

from decimal import Decimal

import pytest

from django_pim.models import FeatureTypeEnum, ProductAttribute, RealProduct
from tests.factories import ChannelFactory, FeatureFactory, FeatureInFeatureSetFactory, FeatureSetFactory

pytestmark = pytest.mark.django_db

BASE = "/api/pim/admin/dec-shop/products/"
CLEARED = [None, "", "   "]


@pytest.fixture
def feature_set():
    ChannelFactory(idx="dec-shop")
    feature_set = FeatureSetFactory(idx="dec-set")
    for idx, feature_type in (("dec-depth", FeatureTypeEnum.DECIMAL), ("dec-note", FeatureTypeEnum.VARCHAR255)):
        feature = FeatureFactory(idx=idx, feature_type=feature_type, scope=3)
        FeatureInFeatureSetFactory(feature_set=feature_set, feature=feature)
    return feature_set


def _create(client, sku: str, attributes: list[dict] | None = None, **extra):
    payload = {"sku": sku, "feature_set_idx": "dec-set", "attributes": attributes or [], **extra}
    return client.post(BASE, payload, format="json")


def _decimals(sku: str) -> list[Decimal]:
    rows = ProductAttribute.objects.filter(product__real_product__sku=sku, feature__idx="dec-depth")
    return [row.value_decimal for row in rows]


class TestCreate:
    @pytest.mark.parametrize("cleared", CLEARED)
    def test_cleared_value_creates_no_row(self, authenticated_client, feature_set, cleared):
        response = _create(authenticated_client, "DEC-C", [{"feature_idx": "dec-depth", "value_decimal": cleared}])

        assert response.status_code == 201, response.content
        assert _decimals("DEC-C") == []

    def test_value_is_stored(self, authenticated_client, feature_set):
        response = _create(authenticated_client, "DEC-V", [{"feature_idx": "dec-depth", "value_decimal": " 12.5 "}])

        assert response.status_code == 201, response.content
        assert _decimals("DEC-V") == [Decimal("12.5")]

    @pytest.mark.parametrize("garbage", ["abc", "NaN", "Infinity", "1,5"])
    def test_garbage_is_400(self, authenticated_client, feature_set, garbage):
        response = _create(authenticated_client, "DEC-G", [{"feature_idx": "dec-depth", "value_decimal": garbage}])

        assert response.status_code == 400, response.content
        assert response.json()["error"] == "VALIDATION_ERROR"
        assert not RealProduct.objects.filter(sku="DEC-G").exists()


class TestUpdate:
    @pytest.fixture(autouse=True)
    def product(self, authenticated_client, feature_set):
        attributes = [
            {"feature_idx": "dec-depth", "value_decimal": "42.5"},
            {"feature_idx": "dec-note", "value_txt": "keep"},
        ]
        assert _create(authenticated_client, "DEC-U", attributes).status_code == 201

    def _patch(self, client, attributes: list[dict]):
        return client.patch(f"{BASE}DEC-U/", {"attributes": attributes}, format="json")

    @pytest.mark.parametrize("cleared", CLEARED)
    def test_cleared_value_removes_the_stored_one(self, authenticated_client, cleared):
        response = self._patch(authenticated_client, [{"feature_idx": "dec-depth", "value_decimal": cleared}])

        assert response.status_code == 200, response.content
        assert _decimals("DEC-U") == []
        assert [a["feature_idx"] for a in response.json()["attributes"]] == ["dec-note"]

    def test_other_features_are_untouched_by_a_clear(self, authenticated_client):
        self._patch(authenticated_client, [{"feature_idx": "dec-depth", "value_decimal": ""}])

        assert ProductAttribute.objects.filter(product__real_product__sku="DEC-U", feature__idx="dec-note").exists()

    def test_absent_key_leaves_the_value(self, authenticated_client):
        response = self._patch(authenticated_client, [{"feature_idx": "dec-depth"}])

        assert response.status_code == 200, response.content
        assert _decimals("DEC-U") == [Decimal("42.5")]

    def test_garbage_is_400_and_keeps_the_value(self, authenticated_client):
        response = self._patch(authenticated_client, [{"feature_idx": "dec-depth", "value_decimal": "abc"}])

        assert response.status_code == 400, response.content
        assert response.json()["error"] == "VALIDATION_ERROR"
        assert _decimals("DEC-U") == [Decimal("42.5")]


class TestSharedDimensions:
    """The product's own width/weight/height/deep (RealProduct) take the same rule."""

    @pytest.mark.parametrize("cleared", [None, "", "  "])
    def test_update_clears_width(self, authenticated_client, feature_set, cleared):
        assert _create(authenticated_client, "DEC-W", width="300.00").status_code == 201

        response = authenticated_client.patch(f"{BASE}DEC-W/", {"width": cleared}, format="json")

        assert response.status_code == 200, response.content
        assert RealProduct.objects.get(sku="DEC-W").width is None

    def test_update_garbage_width_is_400(self, authenticated_client, feature_set):
        assert _create(authenticated_client, "DEC-X", width="300.00").status_code == 201

        response = authenticated_client.patch(f"{BASE}DEC-X/", {"width": "wide"}, format="json")

        assert response.status_code == 400, response.content
        assert RealProduct.objects.get(sku="DEC-X").width == Decimal("300.00")

    def test_create_garbage_weight_is_400(self, authenticated_client, feature_set):
        response = _create(authenticated_client, "DEC-Y", weight="heavy")

        assert response.status_code == 400, response.content
