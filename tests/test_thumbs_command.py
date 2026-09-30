# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`pim-thumbs-generate`: exit codes, summary, --missing-only; resizer creates its TMP_DIR."""

import io
import os
import sys

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from django_pim import settings as pim_settings
from django_pim.models import Picture, PictureThumb, ProductPicture
from django_pim.models.product_picture import PictureRoleEnum
from django_pim.services import product_picture_service
from django_pim.utils.pim_image_resizer import PimImageResizer

from .factories import ChannelFactory, ProductFactory

CONFIG = [(20, 20, "resize ratio, white", "png", 80)]


def _png(color: str) -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), color=color).save(buffer, format="PNG")
    return SimpleUploadedFile(f"{color}.png", buffer.getvalue(), content_type="image/png")


def _picture_on(product, color: str) -> Picture:
    picture = product_picture_service.upload_picture(_png(color))
    ProductPicture.objects.create(product=product, picture=picture, picture_role=PictureRoleEnum.MAIN)
    return picture


@pytest.fixture(autouse=True)
def _env(monkeypatch, settings, tmp_path):
    monkeypatch.setattr(sys, "argv", ["manage.py", "pim-thumbs-generate"])
    monkeypatch.setattr(pim_settings, "THUMBS_CONFIG", CONFIG)
    settings.TMP_DIR = str(tmp_path / "tmp")


@pytest.fixture
def channel(db):
    return ChannelFactory(idx="shop")


def _run(*args: str) -> str:
    out = io.StringIO()
    call_command("pim-thumbs-generate", "shop", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestExitCodes:
    def test_no_pictures_is_an_error_with_summary(self, channel):
        with pytest.raises(CommandError, match="No pictures"):
            _run()

    def test_generates_and_reports(self, channel):
        picture = _picture_on(ProductFactory(shop=channel), "red")

        output = _run()

        assert PictureThumb.objects.filter(picture=picture).count() == 1
        assert "generated 1" in output
        assert "failed 0" in output

    def test_all_failed_is_an_error(self, channel):
        picture = _picture_on(ProductFactory(shop=channel), "red")
        os.remove(picture.image.path)

        with pytest.raises(CommandError, match="failed 1"):
            _run()

    def test_invalid_config_is_an_error(self, channel, monkeypatch):
        monkeypatch.setattr(pim_settings, "THUMBS_CONFIG", None)

        with pytest.raises(CommandError, match="config"):
            _run()

    def test_partial_failure_reports_but_succeeds(self, channel):
        product = ProductFactory(shop=channel)
        broken = _picture_on(product, "red")
        _picture_on(product, "blue")
        os.remove(broken.image.path)

        output = _run()

        assert "generated 1" in output
        assert "failed 1" in output

    def test_sku_scopes_to_one_product(self, channel):
        wanted, other = ProductFactory(shop=channel), ProductFactory(shop=channel)
        _picture_on(wanted, "red")
        _picture_on(other, "blue")

        _run("--sku", wanted.real_product.sku)

        assert PictureThumb.objects.count() == 1


@pytest.mark.django_db
class TestMissingOnly:
    def test_skips_pictures_that_already_have_every_configured_thumb(self, channel):
        product = ProductFactory(shop=channel)
        done, todo = _picture_on(product, "red"), _picture_on(product, "blue")
        PimImageResizer.get_thumbs(done, CONFIG)

        output = _run("--missing-only")

        assert "pictures to process: 1" in output
        assert PictureThumb.objects.filter(picture=todo).count() == 1
        assert "generated 1" in output

    def test_nothing_missing_is_success(self, channel):
        picture = _picture_on(ProductFactory(shop=channel), "red")
        PimImageResizer.get_thumbs(picture, CONFIG)

        output = _run("--missing-only")

        assert "nothing missing" in output.lower()

    def test_no_pictures_at_all_is_still_an_error(self, channel):
        with pytest.raises(CommandError, match="No pictures"):
            _run("--missing-only")

    def test_without_flag_existing_thumbs_are_not_regenerated(self, channel):
        picture = _picture_on(ProductFactory(shop=channel), "red")
        PimImageResizer.get_thumbs(picture, CONFIG)

        output = _run()

        assert "generated 0" in output
        assert PictureThumb.objects.filter(picture=picture).count() == 1


@pytest.mark.django_db
class TestTmpDir:
    def test_resizer_creates_missing_tmp_dir(self, channel, settings, tmp_path):
        settings.TMP_DIR = str(tmp_path / "does" / "not" / "exist")
        picture = _picture_on(ProductFactory(shop=channel), "red")

        PimImageResizer.get_thumb(picture, 20, 20)

        assert os.path.isdir(settings.TMP_DIR)
        assert PictureThumb.objects.filter(picture=picture).count() == 1
