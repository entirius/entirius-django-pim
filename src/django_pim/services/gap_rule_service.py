# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rule-lifecycle reactions for the quality highlighter (etap-03).

Two cost classes, per the szkic:
- **Cheap (severity only)** → ``apply_severity_change``: bulk-update the denormalised severity copy on
  the rule's findings + repair the affected rollups. No catalogue re-detection.
- **Expensive (condition / active / delete)** → mark the catalogue stale so the CMS alert + nightly
  safeguard pick it up; on disable/delete also drop the rule's findings and repair rollups.

The module state (``gaps_rules_changed_at`` vs ``gaps_recomputed_at``) is the single source for the
"rules changed — not recomputed since [date]" alert and for the nightly ``is_catalog_stale`` check.
"""

from __future__ import annotations

from django.utils import timezone

from ..models import GapFinding
from ..models.pim_settings import PimSettings
from . import gap_recompute_service


def apply_severity_change(definition) -> int:
    """Fast path — propagate a rule's new severity to its findings + rollups. Returns rows updated."""
    affected_pks = list(
        GapFinding.objects.filter(definition=definition).values_list("product_id", flat=True).distinct()
    )
    updated = GapFinding.objects.filter(definition=definition).update(severity=definition.severity)
    gap_recompute_service.recompute_rollup_for_products(affected_pks)
    return updated


def cleanup_rule_findings(definition) -> None:
    """Drop a (still-existing) rule's findings and repair the affected rollups. For ``active=False``."""
    affected_pks = list(
        GapFinding.objects.filter(definition=definition).values_list("product_id", flat=True).distinct()
    )
    GapFinding.objects.filter(definition=definition).delete()
    gap_recompute_service.recompute_rollup_for_products(affected_pks)


def mark_rules_changed() -> None:
    """Stamp the catalogue as needing a recompute (drives the CMS alert + nightly safeguard)."""
    PimSettings.load()  # ensure the singleton row exists
    PimSettings.objects.filter(pk=1).update(gaps_rules_changed_at=timezone.now())


def mark_recomputed() -> None:
    """Stamp a completed full recompute."""
    PimSettings.load()
    PimSettings.objects.filter(pk=1).update(gaps_recomputed_at=timezone.now())


def is_catalog_stale() -> bool:
    """True when rules changed after the last full recompute (or it never ran)."""
    s = PimSettings.load()
    if not s.gaps_rules_changed_at:
        return False
    return s.gaps_recomputed_at is None or s.gaps_rules_changed_at > s.gaps_recomputed_at


def get_gaps_settings() -> dict:
    """Operator-tunable gap settings exposed to the CMS (featureset-cascade etap-04)."""
    s = PimSettings.load()
    return {"gaps_skip_default_featureset": s.gaps_skip_default_featureset}


def update_gaps_settings(*, gaps_skip_default_featureset: bool) -> dict:
    """Update the skip-default flag. A real change alters detection outcomes catalogue-wide,
    so it stamps ``gaps_rules_changed_at`` — the CMS "recompute now" alert lights up for free."""
    s = PimSettings.load()
    if s.gaps_skip_default_featureset != gaps_skip_default_featureset:
        PimSettings.objects.filter(pk=1).update(gaps_skip_default_featureset=gaps_skip_default_featureset)
        mark_rules_changed()
    return {"gaps_skip_default_featureset": gaps_skip_default_featureset}


def get_gaps_status() -> dict:
    """Status for the CMS alert: rules-changed vs recomputed + whether a recompute is running."""
    s = PimSettings.load()
    return {
        "gaps_enabled": s.gaps_enabled,
        "rules_changed_at": s.gaps_rules_changed_at.isoformat() if s.gaps_rules_changed_at else None,
        "recomputed_at": s.gaps_recomputed_at.isoformat() if s.gaps_recomputed_at else None,
        "is_stale": is_catalog_stale(),
        "recompute_running": gap_recompute_service.is_full_recompute_running(),
    }
