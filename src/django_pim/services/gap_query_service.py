# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Read queries for gap findings (etap-04).

Powers the per-page bulk findings endpoint: the CMS lists products (rollup columns come inline on the
product response) and then asks here for the "what's missing" labels of the visible page, keyed by
product PK. Sparse by nature — products with no gaps simply have no rows.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from django.db.models import Q

from ..models import GapFinding
from .gap_definition_service import validate_severity


def get_findings_for_products(
    *,
    channel_idx: str,
    product_ids: Iterable[int],
    language: str | None = None,
    severity: str | None = None,
    only_source: bool = False,
) -> dict[int, list[GapFinding]]:
    """Return open findings for the given products in one channel, grouped by product PK.

    - ``language`` keeps language-neutral findings (``language IS NULL``, e.g. pictures) alongside the
      requested language — the CMS asks for one language but neutral gaps always apply.
    - ``severity`` filters to critical/warning (invalid value → ValueError → 400).
    - ``only_source`` drops inherited findings (operator wants source-channel gaps only).
    """
    pks = list(product_ids)
    if not pks:
        return {}
    if severity is not None:
        validate_severity(severity)

    qs = GapFinding.objects.filter(channel_idx=channel_idx, product_id__in=pks).select_related("definition")
    if language:
        qs = qs.filter(Q(language=language) | Q(language__isnull=True))
    if severity:
        qs = qs.filter(severity=severity)
    if only_source:
        qs = qs.filter(inherited=False)

    grouped: dict[int, list[GapFinding]] = defaultdict(list)
    for finding in qs:
        grouped[finding.product_id].append(finding)
    return dict(grouped)
