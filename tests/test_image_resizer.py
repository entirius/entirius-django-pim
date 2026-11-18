# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression: the image resizers passed `Image.ANTIALIAS`, which Pillow 10 removed.

Every call raised `AttributeError`; they use `Image.Resampling.LANCZOS` (the same filter) now.

`PimImageResizer.resize_fill_crop_image` also called a non-existent `Image.pad` for a source larger than the
target in one dimension and smaller in the other.
"""

import pytest
from PIL import Image

from django_pim.utils.image_resizer import ImageResizer
from django_pim.utils.pim_image_resizer import PimImageResizer


def _source(tmp_path, size=(40, 20)):
    path = tmp_path / "src.png"
    Image.new("RGBA", size, color=(0, 128, 128, 255)).save(path)
    return str(path)


def _size(path):
    with Image.open(path) as image:
        return image.size


def test_resize_image_ratio_safe_scales_into_the_box(tmp_path):
    out = str(tmp_path / "out.jpg")
    ImageResizer.resize_image_ratio_safe(_source(tmp_path), out, 20, 20)
    assert _size(out) == (20, 20)


def test_resize_fill_crop_image_fills_the_box(tmp_path):
    out = str(tmp_path / "out.jpg")
    ImageResizer.resize_fill_crop_image(_source(tmp_path), out, 30, 30)
    assert _size(out) == (30, 30)


def test_pim_resize_fill_crop_image_crops_a_larger_source(tmp_path):
    out = str(tmp_path / "out.jpg")
    PimImageResizer.resize_fill_crop_image(_source(tmp_path), out, 10, 10)
    assert _size(out) == (10, 10)


def test_pim_resize_fill_crop_image_pads_a_smaller_source(tmp_path):
    out = str(tmp_path / "out.jpg")
    PimImageResizer.resize_fill_crop_image(_source(tmp_path), out, 60, 60)
    assert _size(out) == (60, 60)


def test_pim_resize_fill_crop_image_crops_and_pads_a_tall_narrow_source(tmp_path):
    out = str(tmp_path / "out.png")
    PimImageResizer.resize_fill_crop_image(_source(tmp_path, size=(10, 40)), out, 30, 20)
    assert _size(out) == (30, 20)
    with Image.open(out) as image:
        assert image.getpixel((0, 10)) == (255, 255, 255)
        assert image.getpixel((15, 10)) == (0, 128, 128)


def test_pim_resize_fill_crop_image_crops_and_pads_a_wide_short_source(tmp_path):
    out = str(tmp_path / "out.png")
    PimImageResizer.resize_fill_crop_image(_source(tmp_path, size=(40, 10)), out, 20, 30)
    assert _size(out) == (20, 30)
    with Image.open(out) as image:
        assert image.getpixel((10, 0)) == (255, 255, 255)
        assert image.getpixel((10, 15)) == (0, 128, 128)


@pytest.mark.parametrize("size", [(30, 40), (60, 20)])
def test_pim_resize_fill_crop_image_crops_when_one_side_equals_the_target(tmp_path, size):
    out = str(tmp_path / "out.png")
    PimImageResizer.resize_fill_crop_image(_source(tmp_path, size=size), out, 30, 20)
    with Image.open(out) as image:
        assert image.size == (30, 20)
        assert image.getpixel((0, 0)) == (0, 128, 128)


@pytest.mark.parametrize("resize", [PimImageResizer.resize_fill_crop_image, ImageResizer.resize_fill_crop_image])
@pytest.mark.parametrize("mode", ["1", "L", "LA", "I;16", "P"])
def test_resize_fill_crop_image_keeping_transparency_pads_every_mode_with_white(tmp_path, resize, mode):
    src = tmp_path / "src.png"
    Image.new(mode, (10, 40)).save(src)
    out = str(tmp_path / "out.png")
    resize(str(src), out, 30, 20, transparency=True)
    with Image.open(out) as image:
        assert image.size == (30, 20)
        assert image.convert("RGB").getpixel((0, 0)) == (255, 255, 255)
