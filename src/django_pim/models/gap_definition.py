# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class GapCheck(models.TextChoices):
    """Keys of the gap-check registry (implemented in etap-02)."""

    FEATURE_PRESENT = "feature_present", "Feature present"
    FEATURE_MIN_LENGTH = "feature_min_length", "Feature minimum length"
    PICTURE_PRESENT = "picture_present", "Picture present"
    PICTURE_MIN_COUNT = "picture_min_count", "Picture minimum count"
    PICTURE_ALT_PRESENT = "picture_alt_present", "Picture alt text present"
    CATEGORY_PRESENT = "category_present", "Category assigned"
    FEATURE_SET_DEFAULT = "feature_set_default", "Feature set is default (placeholder)"


class GapSeverity(models.TextChoices):
    CRITICAL = "critical", "Critical"
    WARNING = "warning", "Warning"


class GapDefinition(BaseModel):
    """Per-client configuration of one quality check (lives in DB, tunable in CMS).

    No logic here — detection reads these rows in the gap_detection_service (etap-02).
    One client = one deployment (one DB), so definitions are just rows.
    """

    key = models.CharField(max_length=64, unique=True)
    # "check" alone is reserved (shadows Model.check() system-check classmethod).
    check_key = models.CharField(max_length=32, choices=GapCheck.choices)
    params = models.JSONField(default=dict, blank=True)
    languages = models.JSONField(null=True, blank=True)
    channels = models.JSONField(null=True, blank=True)
    severity = models.CharField(max_length=16, choices=GapSeverity.choices, db_index=True)
    label_t9n = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["display_order", "key"]
        verbose_name = "gap definition"
        verbose_name_plural = "gap definitions"

    def __str__(self) -> str:
        return f"GapDefinition(key={self.key})"
