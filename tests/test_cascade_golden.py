# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Golden cascade suite — the classification ladder through the enrichment adapter (etap-03).

``test_correctness_golden.py`` proves the detection half (skip-default muting, reassign unlocks
attribute gaps). This file is ADDITIVE and proves the *adapter-driven* ladder the enrichment bus
walks — over the same deterministic golden catalogue, with the bus simulated by a duck-typed
proposal (django-enrichment is deliberately NOT a pim dependency):

    structural finding → find_gaps candidate (feature_set) → apply → recompute →
    attribute findings → second-wave find_gaps candidates → revert → structural again.

Out of scope here, covered elsewhere:
- bus cooldown/dedup of candidates — django-enrichment ``tests/test_task_service.py``,
- adapter unit edges (unknown idx, drift snapshots) — ``test_enrichment_adapter.py``,
- the real cross-module path through the HTTP API — BDD
  ``entirius-tests/features/enrichment/featureset_cascade.feature``.

Assertions are TARGETED (presence/absence for the product under test), per the golden convention.
"""

import os

import pytest
from django.core.management import call_command

from django_pim import models
from django_pim.services import enrichment_adapter as adapter
from django_pim.services import gap_detection_service as svc
from tests import _golden_data as gd
from tests._golden_data import _detect, _keys

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "gaps_golden.yaml")

pytestmark = pytest.mark.django_db


@pytest.fixture
def golden(db):
    """Load the deterministic golden catalogue (channels, features, rules, products)."""
    call_command("loaddata", "--format=yaml", FIXTURE, verbosity=0)


class _Proposal:
    """Duck-typed stand-in for ContentProposal — the adapter only reads these attributes."""

    def __init__(self, *, proposed_value=None, current_snapshot=None):
        self.subject_ref = gd.P_ON_DEFAULT
        self.target_kind = "feature_set"
        self.target_locator = {"channel": gd.CH_SEC}
        self.proposed_value = proposed_value or {}
        self.current_snapshot = current_snapshot or {}
        self.applied_snapshot = {}


def _candidate_refs(definition_key: str) -> list[str]:
    # language-scoped pull on purpose: classification findings are language-neutral (NULL) and
    # must survive the bus's language filter (Q(language__isnull=True) branch).
    return [c["subject_ref"] for c in adapter.find_gaps(definition_key, {}, {"channel": gd.CH_SEC, "language": "en"})]


# --- rung 1: parked on default → exactly one classification candidate ---------


def test_default_set_yields_single_feature_set_candidate(golden):
    _detect(gd.P_ON_DEFAULT)

    candidates = adapter.find_gaps(gd.G_FS_DEFAULT, {}, {"channel": gd.CH_SEC})
    ours = [c for c in candidates if c["subject_ref"] == gd.P_ON_DEFAULT]

    assert len(ours) == 1
    assert ours[0]["target_kind"] == "feature_set"
    assert ours[0]["target_locator"] == {"channel": gd.CH_SEC}
    # Muted attribute checks never materialise → no attribute candidate while unclassified.
    assert gd.P_ON_DEFAULT not in _candidate_refs(gd.G_DESC)


# --- rung 2: apply the classification → attribute gaps become candidates ------


def test_apply_unlocks_second_wave_candidates(golden):
    product = _detect(gd.P_ON_DEFAULT)
    assert gd.G_FS_DEFAULT in _keys(product)  # structural gap present before apply
    snapshot = adapter.read_current(
        subject_ref=gd.P_ON_DEFAULT, target_kind="feature_set", target_locator={"channel": gd.CH_SEC}
    )
    assert snapshot == {"featureset_idx": gd.FS_DEFAULT}  # the drift baseline the bus pins

    adapter.apply(_Proposal(proposed_value={"featureset_idx": gd.FS_FULL}, current_snapshot=snapshot))
    product.refresh_from_db()
    assert product.feature_set.idx == gd.FS_FULL

    # In production the post_save handler enqueues this recompute (gaps_enabled gate + Celery);
    # tests call detection directly to stay synchronous and deterministic.
    svc.detect_for_product(product)
    keys = _keys(product)

    assert gd.G_FS_DEFAULT not in keys  # classified → structural gap gone
    assert gd.G_DESC in keys  # real taxonomy → attribute gaps surface
    assert gd.P_ON_DEFAULT not in _candidate_refs(gd.G_FS_DEFAULT)  # no stale classification candidate
    assert gd.P_ON_DEFAULT in _candidate_refs(gd.G_DESC)  # second wave: fill tasks can spawn
    assert gd.P_ON_DEFAULT in _candidate_refs(gd.G_TAGS)


# --- rung 3: revert → back on default, structural gap returns -----------------


def test_revert_restores_default_and_structural_gap(golden):
    product = _detect(gd.P_ON_DEFAULT)
    snapshot = adapter.read_current(
        subject_ref=gd.P_ON_DEFAULT, target_kind="feature_set", target_locator={"channel": gd.CH_SEC}
    )
    adapter.apply(_Proposal(proposed_value={"featureset_idx": gd.FS_FULL}, current_snapshot=snapshot))
    product.refresh_from_db()
    svc.detect_for_product(product)
    assert gd.G_FS_DEFAULT not in _keys(product)  # middle rung: gap genuinely gone before revert

    adapter.revert(_Proposal(current_snapshot=snapshot))
    product.refresh_from_db()
    svc.detect_for_product(product)

    assert product.feature_set.idx == gd.FS_DEFAULT
    assert _keys(product) == {gd.G_FS_DEFAULT}  # muting back on — single actionable gap
    assert gd.P_ON_DEFAULT in _candidate_refs(gd.G_FS_DEFAULT)
    assert models.GapFinding.objects.filter(product=product).count() == 1
