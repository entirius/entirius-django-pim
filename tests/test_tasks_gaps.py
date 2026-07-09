# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gap Celery tasks + batch recompute + locks (etap-03).

Covers the flush→detect wiring, batch-range == per-product, the full-recompute coalesce lock, and the
nightly safeguard's stale/fresh branches. Tasks are exercised via their inner helpers (no broker).
"""

from unittest.mock import MagicMock, patch

import pytest
from django.db.models import Max, Min

from django_pim import models
from django_pim.models import FeatureScopeEnum, FeatureTypeEnum
from django_pim.models.gap_definition import GapCheck, GapSeverity
from django_pim.models.pim_settings import PimSettings
from django_pim.services import gap_recompute_service
from django_pim.tasks import gaps as gap_tasks
from tests.factories import (
    ChannelFactory,
    CurrencyFactory,
    FeatureFactory,
    GapDefinitionFactory,
    LanguageFactory,
    ProductFactory,
    RealProductFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(db):
    lang = LanguageFactory(iso2="EN", iso3="ENG")
    cur = CurrencyFactory(iso3="EUR")
    return ChannelFactory(idx="ch-tasks", default_language=lang, default_currency=cur)


@pytest.fixture
def missing_description_rule(db):
    FeatureFactory(idx="description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)
    return GapDefinitionFactory(
        key="desc",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )


def _products(channel, n):
    return [ProductFactory(shop=channel, real_product=RealProductFactory()) for _ in range(n)]


# --- flush → detect ----------------------------------------------------------


DRAIN_PATH = "django_pim.signals.dispatch.drain_pending_gap_pks"


def test_flush_drains_pending_and_detects(channel, missing_description_rule):
    products = _products(channel, 2)
    pks = [p.pk for p in products]

    with patch(DRAIN_PATH, return_value=pks):
        result = gap_tasks._flush_gap_recompute()

    assert result["processed"] == 2
    for p in products:
        assert models.GapFinding.objects.filter(product=p).count() == 1


def test_flush_skips_missing_product(channel, missing_description_rule):
    with patch(DRAIN_PATH, return_value=[999999]):
        result = gap_tasks._flush_gap_recompute()
    assert result["processed"] == 0


# --- batch range == per-product ----------------------------------------------


def test_recompute_range_matches_catalogue(channel, missing_description_rule):
    products = _products(channel, 3)
    lo = models.Product.objects.aggregate(m=Min("pk"))["m"]
    hi = models.Product.objects.aggregate(m=Max("pk"))["m"] + 1

    count = gap_recompute_service.recompute_range(lo, hi)

    assert count == 3
    for p in products:
        assert models.GapFinding.objects.filter(product=p).count() == 1


def test_recompute_range_idempotent(channel, missing_description_rule):
    products = _products(channel, 2)
    lo = models.Product.objects.aggregate(m=Min("pk"))["m"]
    hi = models.Product.objects.aggregate(m=Max("pk"))["m"] + 1

    gap_recompute_service.recompute_range(lo, hi)
    gap_recompute_service.recompute_range(lo, hi)  # second pass

    total = models.GapFinding.objects.filter(product__in=products).count()
    assert total == 2  # no duplicates


# --- full-recompute lock coalesce --------------------------------------------


def test_full_lock_second_acquire_coalesces():
    redis_mock = MagicMock()
    redis_mock.set.side_effect = [True, False]  # first acquires, second is blocked
    cache_mock = MagicMock()
    cache_mock.__getitem__.return_value.client.get_client.return_value = redis_mock

    with patch("django_pim.services.gap_recompute_service.caches", cache_mock):
        assert gap_recompute_service.acquire_full_lock() is True
        assert gap_recompute_service.acquire_full_lock() is False


def test_full_lock_degrades_open_when_redis_down():
    with patch("django_pim.services.gap_recompute_service.caches") as mock_caches:
        mock_caches.__getitem__.side_effect = Exception("down")
        assert gap_recompute_service.acquire_full_lock() is True  # never block a backfill


# --- nightly safeguard -------------------------------------------------------


def test_nightly_skips_when_fresh(db):
    PimSettings.load()  # no gaps_rules_changed_at → not stale
    result = gap_tasks._recompute_gaps_nightly()
    assert result == {"skipped": "fresh"}


def test_nightly_recomputes_when_stale_and_stamps_marker(db):
    from django.utils import timezone

    PimSettings.objects.filter(pk=PimSettings.load().pk).update(gaps_rules_changed_at=timezone.now())

    with (
        patch.object(gap_recompute_service, "acquire_full_lock", return_value=True),
        patch.object(gap_recompute_service, "recompute_all", return_value=7) as mock_all,
        patch.object(gap_recompute_service, "release_full_lock") as mock_release,
    ):
        result = gap_tasks._recompute_gaps_nightly()

    assert result == {"recomputed": 7}
    mock_all.assert_called_once()
    mock_release.assert_called_once()
    assert PimSettings.load().gaps_recomputed_at is not None


def test_nightly_skips_when_locked(db):
    from django.utils import timezone

    PimSettings.objects.filter(pk=PimSettings.load().pk).update(gaps_rules_changed_at=timezone.now())
    with patch.object(gap_recompute_service, "acquire_full_lock", return_value=False):
        result = gap_tasks._recompute_gaps_nightly()
    assert result == {"skipped": "locked"}
