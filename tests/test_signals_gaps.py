# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gap signal handlers + GapDefinition lifecycle (etap-03).

Two halves:
- on-save/on-delete of product data enqueues a debounced recompute, gated by the OWN flag
  (independent of Matrix sync), and skipped on raw / suppressed / disabled.
- GapDefinition edits route to the fast path (severity only) or mark the catalogue stale
  (condition/active), and disable/delete clean up findings + repair rollups.
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache

from django_pim import models
from django_pim.models import FeatureScopeEnum, FeatureTypeEnum, ProductAttribute
from django_pim.models.gap_definition import GapCheck, GapSeverity
from django_pim.models.pim_settings import PimSettings
from django_pim.services import gap_detection_service as detect_svc
from django_pim.signals.killswitch import suppress_matrix_signals
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

ENQUEUE_PATH = "django_pim.signals.handlers.enqueue_gap_recompute"


def _enable_gaps():
    s = PimSettings.load()
    s.gaps_enabled = True
    s.save()
    cache.delete("pim:gaps_enabled")


def _disable_gaps():
    s = PimSettings.load()
    s.gaps_enabled = False
    s.save()
    cache.delete("pim:gaps_enabled")


@pytest.fixture
def lang_en(db):
    return LanguageFactory(iso2="EN", iso3="ENG")


@pytest.fixture
def currency(db):
    return CurrencyFactory(iso3="EUR")


@pytest.fixture
def channel(db, lang_en, currency):
    return ChannelFactory(idx="ch-gaps", default_language=lang_en, default_currency=currency)


@pytest.fixture
def description_feature(db):
    return FeatureFactory(idx="description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)


def _product(channel):
    return ProductFactory(shop=channel, real_product=RealProductFactory())


# ─── on-save enqueue ────────────────────────────────────────────────────────


def test_product_save_enqueues_when_enabled(channel):
    _enable_gaps()
    with patch(ENQUEUE_PATH) as mock_enqueue:
        product = _product(channel)
    mock_enqueue.assert_any_call(product.pk)


def test_attribute_save_enqueues_owning_product(channel, description_feature):
    product = _product(channel)
    _enable_gaps()
    with patch(ENQUEUE_PATH) as mock_enqueue:
        ProductAttribute.objects.create(product=product, feature=description_feature, value_txt_t9n={"en": "x"})
    mock_enqueue.assert_any_call(product.pk)


def test_disabled_does_not_enqueue(channel):
    _disable_gaps()
    with patch(ENQUEUE_PATH) as mock_enqueue:
        _product(channel)
    mock_enqueue.assert_not_called()


def test_suppressed_does_not_enqueue(channel):
    _enable_gaps()
    with patch(ENQUEUE_PATH) as mock_enqueue, suppress_matrix_signals():
        _product(channel)
    mock_enqueue.assert_not_called()


def test_gaps_independent_of_matrix_flag(channel):
    """Matrix signals OFF (default) + gaps ON → gap recompute still enqueues."""
    s = PimSettings.load()
    s.matrix_signals_enabled = False
    s.gaps_enabled = True
    s.save()
    cache.delete("pim:matrix_signals_enabled")
    cache.delete("pim:gaps_enabled")

    with patch(ENQUEUE_PATH) as mock_enqueue:
        product = _product(channel)
    mock_enqueue.assert_any_call(product.pk)


# ─── GapDefinition lifecycle ────────────────────────────────────────────────


def _detect(product):
    detect_svc.detect_for_product(product)


def test_severity_only_change_is_fast_path(channel, description_feature):
    # Arrange: product with one CRITICAL finding, rollup populated.
    product = _product(channel)
    definition = GapDefinitionFactory(
        key="sev",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )
    _detect(product)
    finding = models.GapFinding.objects.get(product=product, definition=definition)
    original_pk = finding.pk
    _enable_gaps()

    # Act: change ONLY severity.
    definition.severity = GapSeverity.WARNING
    definition.save()

    # Assert: in-place update (same row), rollup follows, no re-detection (row not replaced).
    finding.refresh_from_db()
    assert finding.pk == original_pk
    assert finding.severity == GapSeverity.WARNING
    product.refresh_from_db()
    assert product.gap_worst_severity == GapSeverity.WARNING


def test_condition_change_marks_stale_not_fast_path(channel, description_feature):
    product = _product(channel)
    definition = GapDefinitionFactory(
        key="cond",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )
    _detect(product)
    _enable_gaps()

    with patch("django_pim.services.gap_rule_service.apply_severity_change") as mock_fast:
        definition.params = {"feature_idx": "name"}
        definition.save()

    mock_fast.assert_not_called()
    assert PimSettings.load().gaps_rules_changed_at is not None


def test_deactivate_cleans_findings(channel, description_feature):
    product = _product(channel)
    definition = GapDefinitionFactory(
        key="off",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )
    _detect(product)
    assert models.GapFinding.objects.filter(product=product).count() == 1
    _enable_gaps()

    definition.active = False
    definition.save()

    assert models.GapFinding.objects.filter(definition=definition).count() == 0
    product.refresh_from_db()
    assert product.gap_count == 0
    assert product.gap_worst_severity is None


def test_delete_rule_repairs_rollup(channel, description_feature):
    product = _product(channel)
    definition = GapDefinitionFactory(
        key="del",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )
    _detect(product)
    _enable_gaps()

    definition.delete()

    assert models.GapFinding.objects.filter(product=product).count() == 0
    product.refresh_from_db()
    assert product.gap_count == 0
    assert product.gap_worst_severity is None


def test_create_rule_marks_stale(db):
    _enable_gaps()
    GapDefinitionFactory(key="new", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})
    assert PimSettings.load().gaps_rules_changed_at is not None
