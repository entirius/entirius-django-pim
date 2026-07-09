# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Concurrency golden manifest — the six safety guards of gap recompute (etap-07).

The highlighter recomputes from signals, a debounce flush, a nightly beat, and the on-demand
"Przelicz teraz" button — these can overlap on the same product or the same catalogue. Four guards
keep that safe (full-recompute lock + debounce coalesce + idempotent per-product replace + disjoint
PK batches); two more invariants keep it from looping (silent rollup) or re-scanning (severity
fast-path).

This file is the consolidated manifest of those six points — ONE representative each, mock +
transactional (no real threads/Redis: deterministic, no flakes). The exhaustive proofs already live
per-stage:
- full-lock coalesce / degrade-open, nightly stale-fresh-locked → ``test_tasks_gaps.py``
- debounce on the own ``pim:gaps:*`` keys + Redis degradation → ``test_signals_gaps_dispatch.py``
- on-save enqueue + GapDefinition lifecycle (fast path / cleanup) → ``test_signals_gaps.py``
- inheritance cleanup after propagation (E2E) → ``test_correctness_golden.py``

"Real" parallelism is proven out-of-band by the shell substitute (two recompute/detect on one
product → no duplicates / no deadlock), documented in the README.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from django_pim import models
from django_pim.models import FeatureScopeEnum, FeatureTypeEnum
from django_pim.models.gap_definition import GapCheck, GapSeverity
from django_pim.models.pim_settings import PimSettings
from django_pim.services import gap_detection_service as svc
from django_pim.services import gap_recompute_service, gap_rule_service
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
    return ChannelFactory(idx="ch-concurrency", default_language=lang, default_currency=cur)


@pytest.fixture
def missing_description_rule(db):
    FeatureFactory(idx="description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)
    return GapDefinitionFactory(
        key="desc",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )


def _product(channel):
    return ProductFactory(shop=channel, real_product=RealProductFactory())


def _enable_gaps():
    settings = PimSettings.load()
    settings.gaps_enabled = True
    settings.save()
    cache.delete("pim:gaps_enabled")


# --- 1. idempotent per-product replace (two runs = same rows) ----------------


def test_detect_for_product_is_idempotent(channel, missing_description_rule):
    product = _product(channel)

    svc.detect_for_product(product)
    svc.detect_for_product(product)  # a full + an on-save recompute racing on one product

    assert models.GapFinding.objects.filter(product=product).count() == 1  # unique key blocks dupes


# --- 2. one lock on the full recompute (second start coalesces) --------------


def test_full_recompute_lock_coalesces_second_start():
    redis_mock = MagicMock()
    redis_mock.set.side_effect = [True, False]  # first acquires, second is blocked
    caches_mock = MagicMock()
    caches_mock.__getitem__.return_value.client.get_client.return_value = redis_mock

    with patch("django_pim.services.gap_recompute_service.caches", caches_mock):
        assert gap_recompute_service.acquire_full_lock() is True
        assert gap_recompute_service.acquire_full_lock() is False  # coalesce, not a second stampede


# --- 3. severity-only change is the fast path (no catalogue re-scan) ---------


def test_severity_change_updates_in_place_without_re_detection(channel, missing_description_rule):
    product = _product(channel)
    svc.detect_for_product(product)
    finding = models.GapFinding.objects.get(product=product)
    original_pk = finding.pk

    missing_description_rule.severity = GapSeverity.WARNING
    updated = gap_rule_service.apply_severity_change(missing_description_rule)

    assert updated == 1
    finding.refresh_from_db()
    assert finding.pk == original_pk  # same row updated in place, not replaced via re-detection
    assert finding.severity == GapSeverity.WARNING
    product.refresh_from_db()
    assert product.gap_worst_severity == GapSeverity.WARNING  # rollup followed the cheap path


# --- 4. cleanup drops a rule's findings and repairs the rollup ---------------


def test_cleanup_rule_findings_clears_and_repairs(channel, missing_description_rule):
    product = _product(channel)
    svc.detect_for_product(product)
    assert models.GapFinding.objects.filter(product=product).count() == 1

    gap_rule_service.cleanup_rule_findings(missing_description_rule)

    assert models.GapFinding.objects.filter(definition=missing_description_rule).count() == 0
    product.refresh_from_db()
    assert product.gap_count == 0
    assert product.gap_worst_severity is None


# --- 5. silent rollup never re-triggers the signal pipeline ------------------


def test_detect_does_not_enqueue_a_recompute_loop(channel, missing_description_rule):
    """The rollup is written via Product.objects.update() — no post_save → no recompute loop."""
    _enable_gaps()
    product = _product(channel)

    with patch("django_pim.signals.handlers.enqueue_gap_recompute") as mock_enqueue:
        svc.detect_for_product(product)

    mock_enqueue.assert_not_called()  # detection writing the rollup must not re-enqueue itself


# --- 6. disjoint PK batches operate only on their own rows (NEW) -------------


def test_disjoint_batches_do_not_touch_each_others_rows(channel, missing_description_rule):
    products = [_product(channel) for _ in range(4)]
    assert models.Product.objects.count() == 4  # isolation: the only products in the PK range
    pks = sorted(p.pk for p in products)
    lo, hi = pks[0], pks[-1] + 1
    mid = pks[2]  # split into two disjoint windows: [lo, mid) and [mid, hi)

    gap_recompute_service.recompute_range(lo, mid)  # first batch only

    first = models.Product.objects.filter(pk__in=pks[:2])
    second = models.Product.objects.filter(pk__in=pks[2:])
    assert all(p.gap_evaluated_at is not None for p in first)  # first window evaluated
    assert all(p.gap_evaluated_at is None for p in second)  # second window untouched
    second_findings_before = models.GapFinding.objects.filter(product__in=second).count()
    assert second_findings_before == 0

    gap_recompute_service.recompute_range(mid, hi)  # second batch

    assert all(p.gap_evaluated_at is not None for p in models.Product.objects.filter(pk__in=pks[2:]))
    # first window's findings are unchanged by the second batch (no overlap, no clobber)
    assert models.GapFinding.objects.filter(product__in=first).count() == 2
