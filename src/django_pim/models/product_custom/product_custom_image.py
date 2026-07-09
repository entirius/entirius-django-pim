# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os.path

from django.db import models, transaction
from django.db.models import Count
from PIL import Image

from django_pim.models.attribute import Attribute
from django_pim.models.product_attribute_image import ProductAttributeImage
from django_pim.settings import TMP_DIR


class ProductAttributeCustomImageManager(models.Manager):
    def get_or_create_image(self, product, attributes):
        feature_with_images = list(
            set(
                ProductAttributeImage.objects.all()
                .select_related("attribute")
                .values_list("attribute__feature__idx", flat=True)
            )
        )
        attr_list = [attr for attr, feature in attributes if feature in feature_with_images]
        attr_count = len(attr_list)
        product_attribute_images = (
            self.filter(product=product, attributes__idx__in=attr_list)
            .annotate(attr_count=Count("attributes"))
            .filter(attr_count=attr_count)
            .first()
        )
        attributes = Attribute.objects.filter(idx__in=attr_list)
        if not product_attribute_images:
            with transaction.atomic():
                product_attribute_images = self.create(product=product, picture=product.main_picture)
                product_attribute_images.attributes.set(attributes)
                product_attribute_images.generate_combined_image()
                product_attribute_images.save()

        return product_attribute_images.picture


class ProductAttributeCustomImage(models.Model):
    product = models.ForeignKey("Product", related_name="product_attribute_custom", on_delete=models.CASCADE)
    attributes = models.ManyToManyField("Attribute", related_name="product_attribute_custom_attr")
    picture = models.ForeignKey("Picture", related_name="product_attribute_custom_picture", on_delete=models.CASCADE)
    objects = ProductAttributeCustomImageManager()

    class Meta:
        ordering = ["product"]
        verbose_name = "Product Custom Image with Attributes"
        verbose_name_plural = "Product Custom Images with Attributes"

    def generate_combined_image(self):
        from django_pim.managers.picture import PictureManager

        main_picture = self.product.main_picture
        if main_picture is None:
            self.picture = main_picture
            raise Exception("Product has no main picture")

        attribute_pictures = ProductAttributeImage.objects.filter(
            attribute__in=self.attributes.all(), product=self.product
        ).order_by("attribute__feature__display_order")

        if not attribute_pictures:
            self.picture = main_picture
            return

        combined_image = Image.open(main_picture.image.path)
        for attr_picture in attribute_pictures:
            attr_picture_pil = Image.open(attr_picture.picture.image.path)
            combined_image.paste(attr_picture_pil, (0, 0), attr_picture_pil)

        picture_path = os.path.join(TMP_DIR, f"combined_image_{self.pk}.png")
        combined_image.save(picture_path)
        picture = PictureManager.get_picture(picture_path)
        self.picture = picture
        self.save()
        os.remove(picture_path)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
