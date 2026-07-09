# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.conf import settings
from django.db import models
from django_utils.models.base_model import BaseModel


class GapExemption(BaseModel):
    """Operator-declared mute of one quality rule for one product (deep mute).

    Detection skips an exempted (definition, language) pair entirely, so the finding is
    never written — the product drops out of badges, rollups and enrichment candidates
    at once. ``language=NULL`` mutes every language of the rule AND the language-neutral
    slot (checks like ``picture_present`` run with ``lang=None``).
    """

    product = models.ForeignKey("Product", related_name="gap_exemptions", on_delete=models.CASCADE)
    definition = models.ForeignKey("GapDefinition", related_name="exemptions", on_delete=models.CASCADE)
    language = models.CharField(max_length=8, null=True, blank=True)  # noqa: DJ001 — NULL = all languages
    reason = models.CharField(max_length=512, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "gap exemption"
        verbose_name_plural = "gap exemptions"
        constraints = [
            # Unlike GapFinding, these rows are operator-created (no idempotent replace to
            # paper over duplicates), so two (product, definition, NULL) rows MUST collide.
            models.UniqueConstraint(
                fields=["product", "definition", "language"],
                name="uniq_gap_exemption",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"GapExemption(product={self.product_id}, def={self.definition_id}, lang={self.language})"
