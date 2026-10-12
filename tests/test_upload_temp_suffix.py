# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The upload services used the uploaded file's name as the suffix of their temp file.

A name with path separators moved the temp file out of the temp directory. The suffix is
the sanitised extension only; the stored record does not depend on it.
"""

import io
import os
import tempfile

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from django_pim.services import product_file_service, product_picture_service
from django_pim.utils.temp_suffix import safe_temp_suffix

HOSTILE_NAMES = [("../../x.pdf", ".pdf"), ("a/b\\c.png", ".png")]


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (11, 13), color="teal").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def temp_paths(monkeypatch):
    """Paths of the temp files the services create, in order."""
    paths = []
    real = tempfile.NamedTemporaryFile

    def recording(*args, **kwargs):
        tmp = real(*args, **kwargs)
        paths.append(tmp.name)
        return tmp

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", recording)
    return paths


def _assert_inside_temp_dir(path: str, extension: str) -> None:
    assert os.path.dirname(os.path.realpath(path)) == os.path.realpath(tempfile.gettempdir())
    assert os.path.splitext(path)[1] == extension
    assert not os.path.exists(path)


@pytest.mark.parametrize(
    ("filename", "suffix"),
    [
        ("report.pdf", ".pdf"),
        ("../../x.pdf", ".pdf"),
        ("a/b\\c.png", ".png"),
        ("archive.tar.gz", ".gz"),
        ("x.p/../d f", ""),
        ("x.pd$f;", ".pdf"),
        (f"x.{'a' * 40}", f".{'a' * 15}"),
        ("no-extension", ""),
        ("trailing.", ""),
        ("..", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_safe_temp_suffix(filename, suffix):
    assert safe_temp_suffix(filename) == suffix


@pytest.mark.django_db
@pytest.mark.parametrize(("hostile_name", "extension"), HOSTILE_NAMES)
def test_file_upload_keeps_temp_file_in_temp_dir(temp_paths, hostile_name, extension):
    file_type = {".pdf": "pdf", ".png": "picture"}[extension]
    content = b"%PDF-1.4 synthetic"

    hostile = product_file_service.upload_file(ContentFile(content, name=hostile_name))
    stored = (hostile.file.name, hostile.file_type, hostile.sha1)
    hostile.delete()
    plain = product_file_service.upload_file(ContentFile(content, name="plain"), file_type=file_type)

    _assert_inside_temp_dir(temp_paths[0], extension)
    assert hostile.original_file_name == hostile_name
    assert (plain.file.name, plain.file_type, plain.sha1) == stored


@pytest.mark.django_db
@pytest.mark.parametrize(("hostile_name", "extension"), HOSTILE_NAMES)
def test_picture_upload_keeps_temp_file_in_temp_dir(temp_paths, hostile_name, extension):
    content = _png()

    hostile = product_picture_service.upload_picture(ContentFile(content, name=hostile_name))
    stored = (hostile.image.name, hostile.sha1)
    hostile.delete()
    plain = product_picture_service.upload_picture(ContentFile(content, name="plain"))

    _assert_inside_temp_dir(temp_paths[0], extension)
    assert hostile.original_file_name == hostile_name
    assert (plain.image.name, plain.sha1) == stored
