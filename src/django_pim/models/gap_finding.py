# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel

from .gap_definition import GapSeverity


class GapFinding(BaseModel):
    """One materialised quality gap. Sparse — only failing checks get a row.

    A product that passes everything has zero rows; the table grows with the
    number of problems, not with the catalogue. Written/cleared by the detection
    service (etap-02) via an idempotent replace per product.
    """

    product = models.ForeignKey("Product", related_name="gap_findings", on_delete=models.CASCADE)
    # No standalone db_index — channel_idx is the leading column of the (channel_idx, severity) composite below.
    channel_idx = models.CharField(max_length=128)
    definition = models.ForeignKey("GapDefinition", related_name="findings", on_delete=models.CASCADE)
    language = models.CharField(max_length=8, null=True, blank=True, db_index=True)  # noqa: DJ001 — NULL = language-neutral (part of unique_together)
    # Denormalised COPY of definition.severity (filter "only critical" without a join).
    severity = models.CharField(max_length=16, choices=GapSeverity.choices, db_index=True)
    inherited = models.BooleanField(default=False, db_index=True)
    source_channel = models.CharField(max_length=128, null=True, blank=True)  # noqa: DJ001 — NULL = not inherited (vs a channel idx)

    class Meta:
        verbose_name = "gap finding"
        verbose_name_plural = "gap findings"
        # NOTE (etap-02/03): Postgres treats NULL as distinct in unique constraints,
        # so two (product, definition, NULL) rows would NOT collide. Harmless here —
        # the detection service does an idempotent delete+insert replace per product.
        unique_together = ("product", "definition", "language")
        # Only the composite is declared here. Single-column needs are already covered:
        # product/definition by their FK auto-indexes, inherited/severity/language by field db_index.
        indexes = [models.Index(fields=["channel_idx", "severity"], name="idx_gapfinding_channel_sev")]

    def __str__(self) -> str:
        return f"GapFinding(product={self.product_id}, def={self.definition_id})"
