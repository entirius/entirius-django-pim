# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django.db.models import Max, Q
from idx_normalizator import validate_idx


class FeatureSetManager(models.Manager):
    def availability_table(self, print_out=True):
        all_objects = self.all()
        tpl = "| {:<6} | {:<48} | {:<48} |"
        tpl_all = "| {:<143} |"
        tpl_row = tpl.replace("|", "+")
        tpl_row = tpl_row.replace(":", ":-")
        tpl_row = tpl_row.replace(" ", "-")
        tpl_row = tpl_row.format("", "", "", "", "", "")

        txts = ["Available features sets:"]
        txts.append(tpl_row)
        txts.append(tpl.format("id", "feature_set.idx", "name"))
        txts.append(tpl_row)
        for config in all_objects:
            txts.append(tpl.format(config.id, config.idx, config.name))
        if len(all_objects) == 0:
            txts.append(tpl_all.format("no features sets are available"))
        txts.append(tpl_row)
        txt = "\n".join(txts)
        if print_out:
            print("\n" + txt, flush=True)
        return txt


class FeatureSet(models.Model):
    # max_length of idx field
    MIN_IDX_LENGTH = 1
    MAX_IDX_LENGTH = 256

    idx = models.CharField(unique=True, max_length=256)
    name = models.CharField(max_length=256, null=False, blank=True, default="")
    desc = models.TextField(blank=True, default="", help_text="Feature Set description for internal use")
    magento_idx = models.CharField(max_length=26, blank=True, null=True)
    magento_pk = models.IntegerField(blank=True, null=True)
    is_default = models.BooleanField(default=False)
    objects = FeatureSetManager()

    def save(self, *args, **kwargs):
        validate_idx(str(self.idx), min_len=self.MIN_IDX_LENGTH, max_len=self.MAX_IDX_LENGTH)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["idx"]
        verbose_name_plural = "features sets"


class FeatureInFeatureSetQuerySet(models.QuerySet):
    def effective_required(self) -> "FeatureInFeatureSetQuerySet":
        """Memberships whose effective flag is True: the override, else the feature's own flag."""
        return self.filter(Q(is_required=True) | Q(is_required__isnull=True, feature__is_required=True))


class FeatureInFeatureSet(models.Model):
    feature_set = models.ForeignKey(
        "FeatureSet",
        related_name="feature_in_feature_set",
        verbose_name="feature_set",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    feature = models.ForeignKey(
        "Feature",
        related_name="feature_in_feature_set",
        verbose_name="feature",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    attributes_group = models.ForeignKey(
        "AttributesGroup", on_delete=models.SET_NULL, null=True, blank=True, related_name="feature_in_sets"
    )

    position = models.IntegerField(null=False, blank=False, default=500)
    is_required = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Per-set override of Feature.is_required. None inherits the feature's flag; "
            "True/False wins for this set only. Not allowed on SYSTEM-scope features."
        ),
    )
    objects = FeatureInFeatureSetQuerySet.as_manager()

    @property
    def effective_is_required(self) -> bool:
        """The override when set, else the feature's own flag."""
        return self.feature.is_required if self.is_required is None else self.is_required

    def validate_override(self) -> None:
        """Raise ValueError when an override sits on a SYSTEM-scope feature (system rules are global)."""
        from .feature import FeatureScopeEnum

        if self.is_required is not None and self.feature.scope == FeatureScopeEnum.SYSTEM:
            raise ValueError(f"Cannot override is_required on system feature '{self.feature.idx}'")

    def save(self, *args, **kwargs):
        self.validate_override()

        def get_last_available_position(feature_set) -> int:
            highest_position = FeatureInFeatureSet.objects.filter(feature_set=feature_set).aggregate(Max("position"))[
                "position__max"
            ]
            return highest_position

        if self.position == 500:
            # Jeżeli nie sprecyzowano position ustaw pozycje na ostatnia dostepna pozycje + 1 nie mniejszą niz 500
            default_start_at = 500
            last_available_position = get_last_available_position(self.feature_set)
            if last_available_position:
                if last_available_position < default_start_at:
                    self.position = default_start_at
                else:
                    self.position = last_available_position + 1
            else:
                self.position = 500

        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "features in features sets"
        constraints = [models.UniqueConstraint(fields=["feature", "feature_set"], name="unique_feature_in_feature_set")]

    def __str__(self):
        return f"{self.feature} - {self.feature_set}"
