# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class ProductVariantGroup(models.Model):
    """One product's own view of an interchangeable-variant axis (product-centric).

    Imported from Magento (a vendor product-variants module). Magento groups are per-flavor matrices with
    several attributes (e.g. weight + units per pack); the public API exposes only a per-SKU
    endpoint returning one "cross" slice per attribute. We store one group per (``owner``, ``feature``)
    so product-detail serves exactly what that SKU's own Magento page shows — otherwise a product
    appears in every overlapping same-label group and the app renders duplicate selectors.
    Members are standalone products of any ``product_class`` related only by sharing the
    differentiating ``feature``. Rebuilt in full per shop on each import, so it carries no Magento
    group id.
    """

    shop = models.ForeignKey(
        "Channel",
        related_name="product_variant_groups",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    owner = models.ForeignKey(
        "Product",
        related_name="owned_variant_groups",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text="Seed product whose Magento endpoint defined this cross; product-detail serves groups by owner.",
    )
    feature = models.ForeignKey(
        "Feature",
        related_name="product_variant_groups",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="The attribute that differentiates members of this group (e.g. weight).",
    )
    name = models.CharField(
        max_length=255, blank=True, null=True, help_text="Magento swatch label, for admin readability only."
    )
    products = models.ManyToManyField(
        "Product",
        through="ProductVariantGroupProduct",
        related_name="variant_groups",
    )
    db_created = models.DateTimeField(auto_now_add=True)
    db_modified = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Backs the "one group per (owner, feature)" invariant in the docstring.
            # Left at the default nulls_distinct=True on purpose: product-detail serves
            # groups by owner, so the duplicate-selector bug this prevents needs a
            # non-NULL owner, and `feature` is on_delete=SET_NULL — under
            # nulls_distinct=False, deleting a Feature that nulls two groups of the same
            # owner would fail with an IntegrityError instead of cleanly orphaning them.
            models.UniqueConstraint(fields=["shop", "owner", "feature"], name="uniq_variant_group_shop_owner_feature")
        ]

    def __str__(self) -> str:
        feature_idx = self.feature.idx if self.feature_id else "?"
        return f"ProductVariantGroup(id={self.id}, feature={feature_idx})"


class ProductVariantGroupProduct(models.Model):
    """Membership of a product in a variant group (M2M-through)."""

    group = models.ForeignKey(
        "ProductVariantGroup",
        related_name="group_products",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "Product",
        related_name="variant_group_memberships",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    position = models.PositiveIntegerField(default=0, help_text="Swatch order, seeded from Attribute.display_order.")

    class Meta:
        unique_together = ("group", "product")
        ordering = ["position"]

    def __str__(self) -> str:
        return f"ProductVariantGroupProduct(group={self.group_id}, product={self.product_id})"
