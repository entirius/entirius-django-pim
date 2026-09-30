# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The legacy /api-viewer/ routes admit staff only — the same rule as the admin API."""

import pytest
from django.urls import reverse

from . import factories

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop():
    return factories.ShopFactory()


@pytest.fixture
def attribute():
    return factories.AttributeFactory(feature=factories.FeatureFactory(), extension={"kept": True})


def _list_url(shop):
    return reverse("admin-category-list", kwargs={"version": "v1", "shop_idx": shop.idx})


def _extension_url(shop, attribute):
    kwargs = {"version": "v1", "shop_idx": shop.idx, "idx": attribute.feature.idx, "attr_idx": attribute.idx}
    return reverse("features-attrs-update", kwargs=kwargs)


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def test_anonymous_get_is_refused(client, shop):
    assert client.get(_list_url(shop)).status_code == 401


def test_anonymous_put_is_refused_and_writes_nothing(client, shop, attribute):
    res = client.put(_extension_url(shop, attribute), data='{"hacked": 1}', content_type="application/json")

    assert res.status_code == 401
    attribute.refresh_from_db()
    assert attribute.extension == {"kept": True}


def test_invalid_token_is_refused(client, shop):
    assert client.get(_list_url(shop), **_auth("not-a-jwt")).status_code == 401


def test_non_staff_user_is_forbidden(client, shop, attribute, regular_token):
    res = client.put(
        _extension_url(shop, attribute), data='{"hacked": 1}', content_type="application/json", **_auth(regular_token)
    )

    assert client.get(_list_url(shop), **_auth(regular_token)).status_code == 403
    assert res.status_code == 403
    attribute.refresh_from_db()
    assert attribute.extension == {"kept": True}


def test_staff_user_reads_and_writes(client, shop, attribute, admin_token):
    res = client.put(
        _extension_url(shop, attribute), data='{"new": 1}', content_type="application/json", **_auth(admin_token)
    )

    assert client.get(_list_url(shop), **_auth(admin_token)).status_code == 200
    assert res.status_code == 200
    attribute.refresh_from_db()
    assert attribute.extension == {"new": 1}
