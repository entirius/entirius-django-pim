# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CRUD for GapDefinition rules (etap-04).

Thin over the ORM: create/update/delete go through ``instance.save()`` / ``instance.delete()`` so
the GapDefinition signal handlers (``signals/handlers.py``) own the rule-lifecycle reactions —
severity-only fast path, mark-stale, cleanup on disable, rollup repair on delete. This service must
NOT call ``gap_rule_service`` itself or it would double-fire those reactions. Validation of
``check_key`` / ``params`` reuses the detection registry (single source of truth).
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from ..models.gap_definition import GapDefinition, GapSeverity
from .gap_check_registry import validate_params

# Sort allowlist — never pass raw user input to order_by().
_ORDERING_MAP: dict[str, str] = {
    "display_order": "display_order",
    "-display_order": "-display_order",
    "key": "key",
    "-key": "-key",
    "severity": "severity",
    "-severity": "-severity",
}

# Mass-assignment whitelist for updates. ``key`` is the immutable identifier — not editable.
_EDITABLE_FIELDS = frozenset(
    {"check_key", "params", "languages", "channels", "severity", "label_t9n", "active", "display_order"}
)

_VALID_SEVERITIES = {s.value for s in GapSeverity}


def validate_severity(severity: str) -> None:
    """Reject a severity outside the GapSeverity enum (shared by every gap filter/create path)."""
    if severity not in _VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity!r}. Allowed: {sorted(_VALID_SEVERITIES)}")


def list_gap_definitions(
    *, search: str | None = None, active: bool | None = None, ordering: str | None = None
) -> QuerySet[GapDefinition]:
    """List gap definitions with optional search/filter and an allowlisted ordering."""
    if ordering is not None and ordering not in _ORDERING_MAP:
        raise ValueError(f"Invalid ordering: {ordering!r}. Allowed: {sorted(_ORDERING_MAP)}")

    qs = GapDefinition.objects.all()
    if search:
        qs = qs.filter(Q(key__icontains=search))
    if active is not None:
        qs = qs.filter(active=active)
    return qs.order_by(_ORDERING_MAP.get(ordering, "display_order"), "key")


def get_gap_definition(key: str) -> GapDefinition:
    """Fetch one definition by key. Raises GapDefinition.DoesNotExist if absent."""
    return GapDefinition.objects.get(key=key)


def create_gap_definition(
    *,
    key: str,
    check_key: str,
    params: dict,
    languages: list[str] | None,
    channels: list[str] | None,
    severity: str,
    label_t9n: dict,
    active: bool,
    display_order: int,
) -> GapDefinition:
    """Create a rule. Validates check_key/params/severity; rejects duplicate key.

    ``.save()`` fires the post_save handler → ``mark_rules_changed`` (a new rule makes the catalogue
    stale until the next recompute).
    """
    validate_params(check_key, params)
    validate_severity(severity)
    if GapDefinition.objects.filter(key=key).exists():
        raise ValueError(f"Gap definition with key {key!r} already exists")

    definition = GapDefinition(
        key=key,
        check_key=check_key,
        params=params,
        languages=languages,
        channels=channels,
        severity=severity,
        label_t9n=label_t9n,
        active=active,
        display_order=display_order,
    )
    definition.save()
    return definition


def update_gap_definition(key: str, updates: dict[str, Any]) -> GapDefinition:
    """Update editable fields of a rule (PATCH semantics — only provided keys).

    Signals decide the cost path: severity-only → fast path, condition/active → mark stale / cleanup.
    """
    invalid = set(updates) - _EDITABLE_FIELDS
    if invalid:
        raise ValueError(f"Fields not editable: {sorted(invalid)}")

    definition = GapDefinition.objects.get(key=key)

    new_check = updates.get("check_key", definition.check_key)
    if "check_key" in updates or "params" in updates:
        validate_params(new_check, updates.get("params", definition.params))
    if "severity" in updates:
        validate_severity(updates["severity"])

    for field, value in updates.items():
        setattr(definition, field, value)
    definition.save()
    return definition


def delete_gap_definition(key: str) -> None:
    """Hard-delete a rule. CASCADE drops its findings; the post_delete handler repairs rollups."""
    definition = GapDefinition.objects.get(key=key)
    definition.delete()
