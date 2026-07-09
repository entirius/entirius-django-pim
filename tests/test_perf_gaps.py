# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Batch recompute calibration (etap-07) — opt-in, deselected by default.

Measures how long ``recompute_range`` takes over a synthetic catalogue, to calibrate the batch size
(``PIM_GAPS_BATCH_SIZE``) and decide whether the nightly safeguard is enough. Marked ``slow`` so the
normal suite skips it (see ``addopts = -m "not slow"`` in pyproject).

Run it explicitly and record the number in the pim-quality-score README:

    PIM_PERF_N=10000 PIM_TEST_DB_HOST=db python -m pytest tests/test_perf_gaps.py -m slow -s -q
"""

import os
import time

import pytest
from django.db.models import Max, Min
from django.utils import timezone

from django_pim import models
from django_pim.models import FeatureScopeEnum, FeatureTypeEnum
from django_pim.models.gap_definition import GapCheck, GapSeverity
from django_pim.models.product import ProductClassEnum
from django_pim.services import gap_recompute_service
from tests.factories import (
    ChannelFactory,
    CurrencyFactory,
    FeatureFactory,
    FeatureSetFactory,
    GapDefinitionFactory,
    LanguageFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.slow]


def test_recompute_range_calibration():
    n = int(os.environ.get("PIM_PERF_N", "10000"))

    lang = LanguageFactory(iso2="EN", iso3="ENG")
    cur = CurrencyFactory(iso3="EUR")
    channel = ChannelFactory(idx="perf-ch", default_language=lang, default_currency=cur)
    feature_set = FeatureSetFactory(idx="perf-fs", name="Perf FS")
    FeatureFactory(idx="description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)
    GapDefinitionFactory(
        key="perf-desc",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
        languages=["en"],
    )

    now = timezone.now()
    reals = models.RealProduct.objects.bulk_create(
        [models.RealProduct(sku=f"perf-{i}", updated_at=now) for i in range(n)], batch_size=2000
    )
    models.Product.objects.bulk_create(
        [
            models.Product(
                real_product=r,
                shop=channel,
                feature_set=feature_set,
                product_class=int(ProductClassEnum.ProductSimple),
                is_enabled=True,
                db_created=now,
                db_modified=now,
            )
            for r in reals
        ],
        batch_size=2000,
    )

    bounds = models.Product.objects.aggregate(lo=Min("pk"), hi=Max("pk"))  # the batch is the whole table here
    lo, hi = bounds["lo"], bounds["hi"] + 1

    start = time.perf_counter()
    processed = gap_recompute_service.recompute_range(lo, hi)
    elapsed = time.perf_counter() - start

    per = 1000 * elapsed / processed if processed else 0
    print(f"\n[perf] recompute_range: {processed} products in {elapsed:.2f}s ({per:.2f} ms/product)")

    assert processed == n
    assert models.GapFinding.objects.filter(product__shop=channel).count() == n  # one gap each
    assert per < 100  # regression alarm (~8.6 ms/product baseline on dev), NOT an SLA
