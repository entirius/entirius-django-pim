# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
ProductFile service layer for business logic.

Upload, link/unlink operations for product file attachments.
"""

import hashlib
import os
import tempfile

from django.core.files import File
from django.db import transaction
from django.db.models import QuerySet

from ..models import Channel, Files, FilesCategory, Product, ProductFile
from ..models.files import FileRoleEnum

FILE_TYPE_MAP = {
    "undefined": FileRoleEnum.UNDEFINED,
    "picture": FileRoleEnum.PICTURE,
    "pdf": FileRoleEnum.PDF,
    "doc": FileRoleEnum.DOC,
    "video": FileRoleEnum.VIDEO,
}

EXTENSION_TO_FILE_ROLE: dict[str, int] = {
    ".pdf": FileRoleEnum.PDF,
    ".doc": FileRoleEnum.DOC,
    ".docx": FileRoleEnum.DOC,
    ".jpg": FileRoleEnum.PICTURE,
    ".jpeg": FileRoleEnum.PICTURE,
    ".png": FileRoleEnum.PICTURE,
    ".gif": FileRoleEnum.PICTURE,
    ".webp": FileRoleEnum.PICTURE,
    ".svg": FileRoleEnum.PICTURE,
    ".mp4": FileRoleEnum.VIDEO,
    ".avi": FileRoleEnum.VIDEO,
    ".mov": FileRoleEnum.VIDEO,
    ".webm": FileRoleEnum.VIDEO,
}


def _detect_file_type_from_name(filename: str) -> int:
    """Detect file type from filename extension."""
    if not filename:
        return FileRoleEnum.UNDEFINED
    ext = os.path.splitext(filename)[1].lower()
    return EXTENSION_TO_FILE_ROLE.get(ext, FileRoleEnum.UNDEFINED)


def _resolve_file_type(file_type_str: str | None) -> int:
    """Convert file type string to enum int value."""
    if file_type_str is None:
        return FileRoleEnum.UNDEFINED
    ft = FILE_TYPE_MAP.get(file_type_str.lower())
    if ft is None:
        raise ValueError(f"Invalid file type: '{file_type_str}'. Valid types: {', '.join(FILE_TYPE_MAP.keys())}")
    return ft


@transaction.atomic
def upload_file(
    file_obj,
    file_category_code: str | None = None,
    file_label: str | None = None,
    file_label_t9n: dict | None = None,
    file_type: str | None = None,
) -> Files:
    """
    Upload a file with SHA1 deduplication.

    If a File with the same SHA1 already exists, returns the existing one.

    Args:
        file_obj: Django UploadedFile object
        file_category_code: Optional file category code
        file_label: Optional custom label
        file_type: File type string (pdf, doc, picture, video, undefined)

    Returns:
        Files instance (new or existing)
    """
    file_obj.seek(0)
    sha1 = hashlib.sha1()
    for chunk in file_obj.chunks():
        sha1.update(chunk)
    sha1_hex = sha1.hexdigest()

    existing = Files.objects.filter(sha1=sha1_hex).first()
    if existing:
        return existing

    category = None
    if file_category_code:
        category = FilesCategory.objects.get(code=file_category_code)

    file_type_enum = _resolve_file_type(file_type)
    if file_type_enum == FileRoleEnum.UNDEFINED and file_obj.name:
        file_type_enum = _detect_file_type_from_name(file_obj.name)

    file_obj.seek(0)

    # Write to a temp file so HashedFileFieldFile can use magic.from_file()
    with tempfile.NamedTemporaryFile(suffix=f"_{file_obj.name}", delete=False) as tmp:
        for chunk in file_obj.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        f = Files(
            file_category=category,
            original_file_name=file_obj.name,
            file_label=file_label,
            file_label_t9n=file_label_t9n or {},
            file_type=file_type_enum,
        )
        with open(tmp_path, "rb") as fh:
            f.file.save(sha1_hex, File(fh))
            f.sha1 = sha1_hex
            f.save()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return f


_UNSET = object()


@transaction.atomic
def update_file(pk: int, file_label_t9n: dict | None = None, file_category_code: str | None = _UNSET) -> Files:
    """
    Update file metadata (label, category).

    Args:
        pk: File primary key
        file_label_t9n: If provided, update multilingual label
        file_category_code: _UNSET = skip, None = clear, str = assign

    Raises:
        Files.DoesNotExist: If file not found
        FilesCategory.DoesNotExist: If category code not found
    """
    f = Files.objects.select_related("file_category").get(pk=pk)

    if file_label_t9n is not None:
        f.file_label_t9n = file_label_t9n
        # Backward compat: set file_label to first non-empty value
        for val in file_label_t9n.values():
            if val:
                f.file_label = val
                break

    if file_category_code is not _UNSET:
        if file_category_code is None:
            f.file_category = None
        else:
            f.file_category = FilesCategory.objects.get(code=file_category_code)

    f.save()
    return Files.objects.select_related("file_category").get(pk=pk)


def list_product_files(channel_idx: str, sku: str) -> QuerySet[ProductFile]:
    """
    List product files for a given product.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)

    return ProductFile.objects.filter(product=product).select_related("file__file_category").order_by("pk")


@transaction.atomic
def link_file_to_product(channel_idx: str, sku: str, file_pk: int) -> ProductFile:
    """
    Link an existing file to a product.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
        Files.DoesNotExist: If file not found
        ValueError: If duplicate link
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    file = Files.objects.get(pk=file_pk)

    if ProductFile.objects.filter(product=product, file=file).exists():
        raise ValueError(f"File {file_pk} is already linked to product '{sku}'")

    pf = ProductFile.objects.create(product=product, file=file)
    return ProductFile.objects.select_related("file__file_category").get(pk=pf.pk)


@transaction.atomic
def unlink_file_from_product(channel_idx: str, sku: str, pk: int) -> dict:
    """
    Unlink a file from a product.

    Deletes the ProductFile association, NOT the Files object itself.
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    pf = ProductFile.objects.get(product=product, pk=pk)
    _, deleted_detail = pf.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result
