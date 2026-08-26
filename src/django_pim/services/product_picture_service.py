# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
ProductPicture service layer for business logic.

Upload, link/unlink, and CRUD operations for product gallery pictures.
"""

import hashlib
import os
import tempfile

from django.core.files import File
from django.db import transaction
from django.db.models import QuerySet

from ..models import Channel, Picture, PictureRoleEnum, Product, ProductPicture
from .lookup_provider import touch_real_product as _touch_real_product

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "position": "position",
    "-position": "-position",
    "picture_role": "picture_role",
    "-picture_role": "-picture_role",
}

ROLE_API_TO_ENUM = {
    "main": PictureRoleEnum.MAIN,
    "general": PictureRoleEnum.GENERAL,
    "variant": PictureRoleEnum.VARIANT,
    "angle": PictureRoleEnum.ANGLE,
    "unknown": PictureRoleEnum.UNKNOWN,
}


def _resolve_role_enum(role_str: str) -> int:
    """Convert API role label to enum int value."""
    role = ROLE_API_TO_ENUM.get(role_str.lower())
    if role is None:
        raise ValueError(f"Invalid picture role: '{role_str}'. Valid roles: {', '.join(ROLE_API_TO_ENUM.keys())}")
    return role


def _resolve_language(language_iso2: str | None):
    """Resolve language ISO2 to Language FK or None."""
    if language_iso2 is None:
        return None
    from django_regional.models import Language

    try:
        return Language.objects.get(iso2=language_iso2.upper())
    except Language.DoesNotExist:
        raise ValueError(f"Language '{language_iso2}' not found") from None


@transaction.atomic
def upload_picture(image_file) -> Picture:
    """
    Upload a picture with SHA1 deduplication.

    If a Picture with the same SHA1 already exists, returns the existing one.

    Uses picture.image.save() explicitly because HashedImageFieldFile needs
    a real file handle (python-magic's from_file requires a filesystem path).

    Args:
        image_file: Django UploadedFile object

    Returns:
        Picture instance (new or existing)
    """
    image_file.seek(0)
    sha1 = hashlib.sha1()
    for chunk in image_file.chunks():
        sha1.update(chunk)
    sha1_hex = sha1.hexdigest()

    existing = Picture.objects.filter(sha1=sha1_hex).first()
    if existing:
        return existing

    image_file.seek(0)

    # Write to a temp file so HashedImageFieldFile can use magic.from_file()
    with tempfile.NamedTemporaryFile(suffix=f"_{image_file.name}", delete=False) as tmp:
        for chunk in image_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        picture = Picture(original_file_name=image_file.name)
        with open(tmp_path, "rb") as f:
            picture.image.save(sha1_hex, File(f))
            picture.save()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return picture


def list_product_pictures(
    channel_idx: str, sku: str, role: str | None = None, ordering: str | None = None
) -> QuerySet[ProductPicture]:
    """
    List product pictures for a given product.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)

    queryset = ProductPicture.objects.filter(product=product).select_related("picture", "language")

    if role:
        role_enum = _resolve_role_enum(role)
        queryset = queryset.filter(picture_role=role_enum)

    order_field = ORDERING_MAP.get(ordering, "position") if ordering else "position"
    queryset = queryset.order_by(order_field)

    return queryset


def get_product_picture(channel_idx: str, sku: str, pk: int) -> ProductPicture:
    """
    Get a single product picture.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
        ProductPicture.DoesNotExist: If not found
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)

    return ProductPicture.objects.select_related("picture", "language").get(product=product, pk=pk)


@transaction.atomic
def link_picture_to_product(
    channel_idx: str,
    sku: str,
    picture_pk: int,
    picture_role: str = "general",
    position: int = 0,
    language_iso2: str | None = None,
    alt_text_t9n: dict | None = None,
) -> ProductPicture:
    """
    Link an existing picture to a product.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
        Picture.DoesNotExist: If picture not found
        ValueError: If role/language constraints violated
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    picture = Picture.objects.get(pk=picture_pk)
    role_enum = _resolve_role_enum(picture_role)
    language = _resolve_language(language_iso2)

    pp = ProductPicture.objects.create(
        product=product,
        picture=picture,
        picture_role=role_enum,
        language=language,
        position=position,
        alt_text_t9n=alt_text_t9n or {},
    )

    _touch_real_product(product.real_product_id)
    return ProductPicture.objects.select_related("picture", "language").get(pk=pp.pk)


@transaction.atomic
def update_product_picture(channel_idx: str, sku: str, pk: int, **fields: object) -> ProductPicture:
    """Update a product picture assignment."""
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    pp = ProductPicture.objects.get(product=product, pk=pk)

    if "picture_role" in fields and fields["picture_role"] is not None:
        pp.picture_role = _resolve_role_enum(fields.pop("picture_role"))

    if "language_iso2" in fields:
        lang_val = fields.pop("language_iso2")
        pp.language = _resolve_language(lang_val)

    for field, value in fields.items():
        if value is not None:
            setattr(pp, field, value)
    pp.save()

    _touch_real_product(product.real_product_id)
    return ProductPicture.objects.select_related("picture", "language").get(pk=pp.pk)


@transaction.atomic
def unlink_picture_from_product(channel_idx: str, sku: str, pk: int) -> dict:
    """
    Unlink a picture from a product.

    Deletes the ProductPicture association, NOT the Picture itself.
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    pp = ProductPicture.objects.get(product=product, pk=pk)
    _, deleted_detail = pp.delete()
    _touch_real_product(product.real_product_id)
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result
