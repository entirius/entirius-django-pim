# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Golden correctness suite — the named safety net for gap-detection (etap-07).

A bad gap silently wastes operator trust and (later) enrichment spend, so correctness gets its own
consolidated, fixtures-driven suite ABOVE the per-stage tests. Per-stage tests already prove most of
the rules (``test_services.py`` covers own-vs-inherited, custom skip, FeatureSet applicability,
bool/select/text emptiness, cross-language masking); this file is ADDITIVE and focuses on the cases
they do NOT cover end-to-end:

- inheritance cleanup after a fix-on-default propagates to the child,
- per-type emptiness for MULTISELECT and DECIMAL (only bool/select/text were tested before),

plus a compact manifest of the four golden rules over one deterministic catalogue
(``tests/fixtures/gaps_golden.yaml``, mirrored in entirius-test-package).

Assertions are TARGETED — every active definition runs against every product, so we assert the
presence/absence of the specific finding under test (by definition key), not exact totals.
"""

import os

import pytest
from django.core.management import call_command

from django_pim import models
from django_pim.services import gap_detection_service as svc
from django_pim.services import inheritance_service
from tests import _golden_data as gd

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "gaps_golden.yaml")

pytestmark = pytest.mark.django_db


@pytest.fixture
def golden(db):
    """Load the deterministic golden catalogue (channels, features, rules, products)."""
    call_command("loaddata", "--format=yaml", FIXTURE, verbosity=0)


# --- helpers (shared with test_cascade_golden via _golden_data) ---------------

_product = gd._product
_detect = gd._detect
_keys = gd._keys


# --- FeatureSet applicability + feature_present ------------------------------


def test_feature_set_applicability(golden):
    # Empty FeatureSet → BU-feature rules are "nie dotyczy"; SYSTEM description still applies.
    product = _detect(gd.P_MISSING_DESC)
    keys = _keys(product)

    assert gd.G_DESC in keys  # SYSTEM feature, missing → gap
    assert gd.G_MATERIAL not in keys  # BU feature not in the FeatureSet → not applicable
    assert gd.G_TAGS not in keys
    assert gd.G_WEIGHT not in keys


def test_present_and_long_description_is_ok(golden):
    product = _detect(gd.P_DESC_OK)
    product.refresh_from_db()
    keys = _keys(product)

    assert gd.G_DESC not in keys
    assert gd.G_DESC_MIN not in keys
    assert product.gap_evaluated_at is not None  # evaluated, genuinely OK on description


def test_short_description_trips_min_length_only(golden):
    product = _detect(gd.P_SHORT_DESC)
    keys = _keys(product)

    assert gd.G_DESC_MIN in keys  # too short
    assert gd.G_DESC not in keys  # but present → no "missing" gap


# --- ProductCustom: "nieoceniony" vs "OK" ------------------------------------


def test_custom_is_unevaluated_but_runs_non_attribute_checks(golden):
    product = _detect(gd.P_CUSTOM)
    keys = _keys(product)

    product.refresh_from_db()
    assert product.gap_evaluated_at is None  # NULL distinguishes "nieoceniony" from a genuine OK
    assert gd.G_DESC not in keys  # attribute checks skipped for custom
    assert gd.G_PICTURE in keys  # non-attribute check (picture) still runs


# --- per-type emptiness: MULTISELECT -----------------------------------------


def test_multiselect_empty_is_a_gap(golden):
    assert gd.G_TAGS in _keys(_detect(gd.P_MULTI_EMPTY))


def test_multiselect_with_one_selection_is_ok(golden):
    assert gd.G_TAGS not in _keys(_detect(gd.P_MULTI_FILLED))


# --- per-type emptiness: DECIMAL (0 is a value) ------------------------------


def test_decimal_zero_is_a_value_not_empty(golden):
    assert gd.G_WEIGHT not in _keys(_detect(gd.P_DECIMAL_ZERO))


def test_decimal_missing_row_is_a_gap(golden):
    assert gd.G_WEIGHT in _keys(_detect(gd.P_DECIMAL_MISSING))


# --- inheritance: own vs inherited + source_channel, then cleanup (E2E) ------


def test_inherited_gap_points_to_default_then_clears_after_propagation(golden):
    """The full inheritance story end-to-end: an empty inheriting child reports an *inherited* gap
    tagged with where to fix it (the default channel); once the default's value is materialised onto
    the child, the gap clears. The propagation *enqueue* mechanism is unit-tested in test_services.py;
    here we prove the detection-level end state across the whole flow.
    """
    child = _detect(gd.P_INHERIT, gd.CH_SEC)
    source = _product(gd.P_INHERIT, gd.CH_DEFAULT)

    before = models.GapFinding.objects.get(product=child, definition__key=gd.G_MATERIAL)
    assert before.inherited is True  # gap shown on the child, but flagged as inherited
    assert before.source_channel == gd.CH_DEFAULT  # operator told where to fix it

    # Real propagation path: copy the default's values onto inheriting children of the same SKU.
    inheritance_service.propagate_to_inheriting_products(source)
    svc.detect_for_product(child)

    assert gd.G_MATERIAL not in _keys(child)  # the fix on default cleared the child's inherited gap


# --- featureset-cascade: skip-default sequencing (etap-01) --------------------


def test_product_on_default_set_reports_only_structural_gap(golden):
    """Flag on (default): the placeholder set mutes everything except the classification gap."""
    product = _detect(gd.P_ON_DEFAULT)

    # desc missing + picture missing would both fire — suppressed; exactly ONE actionable gap.
    assert _keys(product) == {gd.G_FS_DEFAULT}


def test_flag_off_structural_coexists_with_other_checks(golden):
    """gaps_skip_default_featureset=False only disables the muting — the structural gap stays."""
    settings = models.PimSettings.load()
    settings.gaps_skip_default_featureset = False
    settings.save()

    keys = _keys(_detect(gd.P_ON_DEFAULT))

    assert gd.G_FS_DEFAULT in keys  # structural gap still fails on the default set
    assert gd.G_DESC in keys  # ...and the muted checks reappear
    assert gd.G_PICTURE in keys


def test_reassign_to_real_set_unlocks_attribute_gaps(golden):
    """The cascade step: assign a real set → structural gap clears, attribute gaps light up."""
    product = _detect(gd.P_ON_DEFAULT)
    assert _keys(product) == {gd.G_FS_DEFAULT}

    fs_full = models.FeatureSet.objects.get(idx=gd.FS_FULL)
    models.Product.objects.filter(pk=product.pk).update(feature_set=fs_full)  # silent, no signal loop
    product.refresh_from_db()
    svc.detect_for_product(product)

    keys = _keys(product)
    assert gd.G_FS_DEFAULT not in keys  # classified → structural gap gone
    assert gd.G_DESC in keys  # real taxonomy → attribute gaps now meaningful
    assert gd.G_TAGS in keys  # BU features of the full set apply
    assert gd.G_PICTURE in keys


# --- fixture-drift guard -----------------------------------------------------


def test_golden_fixture_source_still_matches_models(db):
    """Build the fixture from its regenerable source against the current schema.

    The YAML loaded above is a static artefact; if a migration adds a required field or changes an
    enum, this fails loudly here (and tells you to re-run emit_fixture) instead of surfacing as a
    cryptic loaddata error in every other test. Runs in the test transaction → rolled back.
    """
    gd.build_golden_objects()

    assert models.GapDefinition.objects.filter(key__startswith="golden-").count() == 7
    assert models.Product.objects.count() == 11  # the catalogue the YAML mirrors
