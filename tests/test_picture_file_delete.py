# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression: model `delete()` overrides referenced a non-existent `self.thumbs` accessor.

`Picture.delete()` / `Files.delete()` used to raise `AttributeError` on EVERY call (the reverse
accessor is `picture_thumbs`, and `Files` has no thumbnails at all), so normal deletes crashed and
thumbnail rows/files leaked. These pin the fixed behaviour.

Image/file-backed models go through a temp file because `HashedImageField`/`HashedFileField` run
`magic.from_file()` on save (needs a real filesystem path) — same trick as
`product_picture_service.upload_picture`.
"""

import io
import os
import tempfile

import pytest
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from django_pim.models.files import Files
from django_pim.models.picture import Picture
from django_pim.models.picture_thumb import PictureThumb
from django_pim.models.thumb import Thumb
from django_pim.services import product_picture_service


def _png(name: str, color: str = "red") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=color).save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/png")


def _save_via_tempfile(instance, field_name: str, upload: SimpleUploadedFile):
    """Persist a HashedImage/File-backed model the way magic.from_file() needs (real path)."""
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
def test_picture_delete_removes_thumbs_and_does_not_raise():
    picture = product_picture_service.upload_picture(_png("pic.png", "red"))
    thumb = _save_via_tempfile(Thumb(), "image", _png("thu.png", "blue"))
    join = PictureThumb.objects.create(
        picture=picture, thumb=thumb, transform_method="resize ratio, white", out_format="png"
    )
    thumb_pk, join_pk = thumb.pk, join.pk

    picture.delete()  # previously raised AttributeError: 'Picture' object has no attribute 'thumbs'

    assert not Picture.objects.filter(pk=picture.pk).exists()
    assert not Thumb.objects.filter(pk=thumb_pk).exists()  # thumbnail (and its file) cleaned up
    assert not PictureThumb.objects.filter(pk=join_pk).exists()  # join cascaded away


@pytest.mark.django_db
def test_files_delete_does_not_raise():
    files = _save_via_tempfile(Files(), "file", SimpleUploadedFile("doc.pdf", b"%PDF-1.4 test"))
    pk = files.pk

    files.delete()  # previously raised AttributeError: 'Files' object has no attribute 'thumbs'

    assert not Files.objects.filter(pk=pk).exists()
