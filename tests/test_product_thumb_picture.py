# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression: `Product.thumb_picture` referenced the non-existent `thumbs` accessor.

Same mistake as the `delete()` overrides in `test_picture_file_delete.py` — the reverse
accessor from Picture is `picture_thumbs`. This one sits in a property rather than a
delete, so instead of crashing a delete it raised on every read, and
`product_in_category_service._get_thumbnail_url` swallows the AttributeError into None.

Images go through a temp file because `HashedImageField` runs `magic.from_file()` on save,
the same trick the picture-delete tests use.
"""

import io
import os
import tempfile

import pytest
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from django_pim.models.picture_thumb import PictureThumb
from django_pim.models.product_picture import PictureRoleEnum, ProductPicture
from django_pim.models.thumb import Thumb
from django_pim.services import product_picture_service

from .factories import ProductFactory


def _png(name: str, color: str = "red") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=color).save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/png")


def _save_via_tempfile(instance, field_name: str, upload: SimpleUploadedFile):
    upload.seek(0)
    with tempfile.NamedTemporaryFile(suffix=f"_{upload.name}", delete=False) as tmp:
        tmp.write(upload.read())
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as handle:
            getattr(instance, field_name).save(upload.name, File(handle))
            instance.save()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return instance


@pytest.mark.django_db
def test_thumb_picture_returns_the_thumb_row_and_does_not_raise():
    product = ProductFactory()
    picture = product_picture_service.upload_picture(_png("main.png", "red"))
    ProductPicture.objects.create(product=product, picture=picture, picture_role=PictureRoleEnum.MAIN)
    thumb = _save_via_tempfile(Thumb(), "image", _png("thu.png", "blue"))
    join = PictureThumb.objects.create(
        picture=picture, thumb=thumb, transform_method="resize ratio, white", out_format="png"
    )

    # previously raised AttributeError: 'Picture' object has no attribute 'thumbs'
    assert product.thumb_picture == join


@pytest.mark.django_db
def test_thumb_picture_is_none_when_the_main_picture_has_no_thumb():
    product = ProductFactory()
    picture = product_picture_service.upload_picture(_png("main.png", "green"))
    ProductPicture.objects.create(product=product, picture=picture, picture_role=PictureRoleEnum.MAIN)

    assert product.thumb_picture is None


@pytest.mark.django_db
def test_thumb_picture_is_none_when_there_is_no_main_picture():
    assert ProductFactory().thumb_picture is None
