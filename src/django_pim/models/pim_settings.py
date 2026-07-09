# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class PimSettings(models.Model):
    """Singleton settings for PIM behavior. Managed via Django admin (Grappelli) only."""

    matrix_signals_enabled = models.BooleanField(
        default=False, help_text="Enable automatic Matrix read model sync on PIM changes"
    )

    # --- Quality gaps highlighter (etap-03) ---
    # Own gate, independent of matrix_signals_enabled: the gap recompute tor must run even
    # for clients with Matrix sync OFF (the default).
    gaps_enabled = models.BooleanField(default=False, help_text="Enable automatic quality-gap recompute on PIM changes")
    # Bumped when a rule's condition/active changes (or a wide cascade invalidates the catalogue).
    # Drives the CMS "rules changed — quality not recomputed since [date]" alert + the nightly safeguard.
    gaps_rules_changed_at = models.DateTimeField(null=True, blank=True)
    # Set when a full catalogue recompute finishes. Compared against gaps_rules_changed_at.
    gaps_recomputed_at = models.DateTimeField(null=True, blank=True)
    # Cascade sequencing (featureset-cascade etap-01): while a product sits on the default
    # (placeholder) feature set, run ONLY the structural `feature_set_default` check and mute
    # everything else — attribute/picture gaps computed on the wrong taxonomy are noise.
    gaps_skip_default_featureset = models.BooleanField(
        default=True,
        help_text=(
            "While a product is on the default (placeholder) feature set, report only the "
            "'assign a real feature set' gap and suppress all other checks."
        ),
    )

    class Meta:
        verbose_name = "PIM Settings"
        verbose_name_plural = "PIM Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "PimSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return "PIM Settings"
