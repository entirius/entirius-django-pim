# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for the admin category list (lazy-tree fields, correlated counts, search).

URL: GET /api/pim/v2/admin/{channel_idx}/categories/
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from django_pim.models import ProductCategory
from tests.factories import ChannelFactory, ProductCategoryFactory, ProductFactory, ProductInCategoryFactory

BASE_URL = "/api/pim/v2/admin"


@pytest.fixture
def channel(db):
    return ChannelFactory(idx="tree-channel")


def make_category(channel, idx, parent=None, position=None, is_active=True, **names):
    return ProductCategoryFactory(
        shop=channel,
        idx=idx,
        parent_category=parent,
        position=position,
        is_active=is_active,
        tree_deep=0 if parent is None else parent.tree_deep + 1,
        name_t9n=names or {"pl": idx.title()},
    )


def get_list(client, channel, query=""):
    response = client.get(f"{BASE_URL}/{channel.idx}/categories/{query}")
    assert response.status_code == 200, response.content
    return response.json()


def idxs(data):
    return [item["idx"] for item in data["results"]]


@pytest.mark.django_db
class TestTreeFields:
    def test_root_item_shape(self, authenticated_client, channel):
        make_category(channel, "root", position=3)
        item = get_list(authenticated_client, channel)["results"][0]
        assert item["subcategory_count"] == 0
        assert item["position"] == 3
        assert item["parent_category_idx"] is None
        assert item["parent_category"] is None
        assert {"pk", "idx", "name", "is_active", "is_in_menu", "url_key", "product_count", "desc"} <= set(item)

    def test_position_may_be_null(self, authenticated_client, channel):
        make_category(channel, "no-position", position=None)
        assert get_list(authenticated_client, channel)["results"][0]["position"] is None

    def test_parent_and_subcategory_counts(self, authenticated_client, channel):
        root = make_category(channel, "root", position=1)
        child_a = make_category(channel, "child-a", parent=root, position=1)
        make_category(channel, "child-b", parent=root, position=2)
        make_category(channel, "grandchild", parent=child_a, position=1)
        items = {i["idx"]: i for i in get_list(authenticated_client, channel)["results"]}
        assert items["root"]["subcategory_count"] == 2  # direct children only
        assert items["child-a"]["subcategory_count"] == 1
        assert items["child-b"]["subcategory_count"] == 0
        assert items["child-a"]["parent_category_idx"] == "root"
        assert items["child-a"]["parent_category"] == root.pk
        assert items["grandchild"]["parent_category_idx"] == "child-a"

    def test_subcategory_count_ignores_inactive_and_other_channels(self, authenticated_client, channel):
        root = make_category(channel, "root")
        make_category(channel, "inactive-child", parent=root, is_active=False)
        other = ChannelFactory(idx="other-channel")
        make_category(other, "foreign-root")
        data = get_list(authenticated_client, channel)
        assert {i["idx"]: i["subcategory_count"] for i in data["results"]}["root"] == 1
        assert "foreign-root" not in idxs(data)

    def test_product_count_value(self, authenticated_client, channel):
        full = make_category(channel, "full", position=1)
        empty = make_category(channel, "empty", position=2)
        for _ in range(3):
            ProductInCategoryFactory(category=full, product=ProductFactory(shop=channel))
        items = {i["idx"]: i["product_count"] for i in get_list(authenticated_client, channel)["results"]}
        assert items == {"full": 3, "empty": 0}
        assert empty.pk


@pytest.mark.django_db
class TestSearch:
    @pytest.fixture(autouse=True)
    def categories(self, channel):
        make_category(channel, "shoes", position=1, en="Running shoes", pl="Buty do biegania")
        make_category(channel, "hats", position=2, en="Hats", pl="Czapki")
        make_category(channel, "sku-123", position=3, en="Misc", pl="Rozne")

    def test_matches_name_value_case_insensitive(self, authenticated_client, channel):
        assert idxs(get_list(authenticated_client, channel, "?search=RUNNING")) == ["shoes"]

    def test_matches_any_channel_language(self, authenticated_client, channel):
        assert idxs(get_list(authenticated_client, channel, "?search=czapki")) == ["hats"]
        assert idxs(get_list(authenticated_client, channel, "?search=biegania")) == ["shoes"]

    def test_language_key_does_not_match(self, authenticated_client, channel):
        data = get_list(authenticated_client, channel, "?search=pl")
        assert "hats" not in idxs(data)
        assert get_list(authenticated_client, channel, "?search=en")["count"] == 0  # no name or idx contains "en"

    def test_json_punctuation_does_not_match(self, authenticated_client, channel):
        assert get_list(authenticated_client, channel, '?search=":')["count"] == 0

    def test_matches_idx(self, authenticated_client, channel):
        assert idxs(get_list(authenticated_client, channel, "?search=SKU-12")) == ["sku-123"]

    def test_name_and_idx_hits_are_combined(self, authenticated_client, channel):
        make_category(channel, "running-gear", position=4, en="Gear")
        assert sorted(idxs(get_list(authenticated_client, channel, "?search=running"))) == ["running-gear", "shoes"]

    def test_like_wildcards_are_literal(self, authenticated_client, channel):
        assert get_list(authenticated_client, channel, "?search=%25")["count"] == 0


@pytest.mark.django_db
class TestUnchangedBehaviour:
    @pytest.fixture(autouse=True)
    def tree(self, channel):
        self.root_a = make_category(channel, "b-root", position=2)
        self.root_b = make_category(channel, "a-root", position=1, is_active=False)
        self.child = make_category(channel, "child", parent=self.root_a, position=1)

    def test_root_only(self, authenticated_client, channel):
        assert idxs(get_list(authenticated_client, channel, "?root_only=true")) == ["a-root", "b-root"]

    def test_parent_category(self, authenticated_client, channel):
        assert idxs(get_list(authenticated_client, channel, f"?parent_category={self.root_a.pk}")) == ["child"]

    def test_is_active(self, authenticated_client, channel):
        assert idxs(get_list(authenticated_client, channel, "?is_active=false")) == ["a-root"]

    def test_default_order_is_position_then_idx(self, authenticated_client, channel):
        make_category(channel, "z-first", position=1)
        assert idxs(get_list(authenticated_client, channel)) == ["a-root", "child", "z-first", "b-root"]

    def test_ordering_param_and_pagination(self, authenticated_client, channel):
        data = get_list(authenticated_client, channel, "?ordering=-idx&page_size=2")
        assert idxs(data) == ["child", "b-root"]
        assert data["count"] == 3
        assert data["next"]


@pytest.mark.django_db
class TestQueryCount:
    def _queries_for_page(self, client, channel, page_size):
        with CaptureQueriesContext(connection) as ctx:
            data = get_list(client, channel, f"?page_size={page_size}&search=cat")
        assert len(data["results"]) == page_size
        return len(ctx)

    def test_query_count_is_constant_per_page_size(self, authenticated_client, channel):
        root = make_category(channel, "cat-root", en="Cat root")
        ProductCategory.objects.bulk_create(
            ProductCategory(
                shop=channel, idx=f"cat-{n}", parent_category=root, tree_deep=1, position=n, name_t9n={"en": f"Cat {n}"}
            )
            for n in range(30)
        )
        for category in ProductCategory.objects.filter(shop=channel)[:5]:
            ProductInCategoryFactory(category=category, product=ProductFactory(shop=channel))
        small = self._queries_for_page(authenticated_client, channel, 2)
        large = self._queries_for_page(authenticated_client, channel, 25)
        assert small == large
        assert large <= 8  # auth + channel(+languages) + count + page
