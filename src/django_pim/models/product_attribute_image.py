# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models

from django_pim.models import Attribute, Picture, Product


class ProductAttributeImage(models.Model):
    product: Product = models.ForeignKey(
        "Product", related_name="product_attribute_images", on_delete=models.CASCADE, null=True, blank=True
    )
    attribute: Attribute = models.ForeignKey("Attribute", related_name="attribute_picture", on_delete=models.CASCADE)
    picture: Picture = models.ForeignKey(
        "Picture", related_name="product_attribute_picture", on_delete=models.CASCADE, null=True, blank=True
    )
    color_hash = models.CharField(max_length=64, null=True, blank=True)
    objects = models.Manager()

    class Meta:
        unique_together = ("product", "attribute")
        ordering = ["product"]
        verbose_name = "Product Attribute Image"
        verbose_name_plural = "Product Attribute Images"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            super().save(*args, **kwargs)
        else:
            old_obj = ProductAttributeImage.objects.get(pk=self.pk)
            if old_obj.attribute_id != self.attribute_id:
                super().save(*args, **kwargs)
                self._clean_custom_images()
            else:
                super().save(*args, **kwargs)
        if is_new:
            self._clean_custom_images()

    def _clean_custom_images(self):
        """
        Usuwa wszystkie wpisy z ProductAttributeCustomImage powiązane z atrybutem tego obiektu.
        """
        from django_pim.models import ProductAttributeCustomImage

        ProductAttributeCustomImage.objects.filter(attributes=self.attribute).delete()
