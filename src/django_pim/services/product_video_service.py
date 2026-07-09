# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
ProductVideo service layer for business logic.

CRUD operations for product video assignments (YouTube/Vimeo URLs).
"""

from django.db import transaction
from django.db.models import QuerySet

from ..models import Channel, Product, ProductVideo, Video
from ..models.product_video import VideoRoleEnum

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "position": "position",
    "-position": "-position",
    "video_role": "video_role",
    "-video_role": "-video_role",
}

ROLE_API_TO_ENUM = {"main": VideoRoleEnum.MAIN, "variant": VideoRoleEnum.VARIANT, "unknown": VideoRoleEnum.UNKNOWN}


def _resolve_role_enum(role_str: str) -> int:
    """Convert API role label to enum int value."""
    role = ROLE_API_TO_ENUM.get(role_str.lower())
    if role is None:
        raise ValueError(f"Invalid video role: '{role_str}'. Valid roles: {', '.join(ROLE_API_TO_ENUM.keys())}")
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


def list_product_videos(
    channel_idx: str, sku: str, role: str | None = None, ordering: str | None = None
) -> QuerySet[ProductVideo]:
    """
    List product videos for a given product.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)

    queryset = ProductVideo.objects.filter(product=product).select_related("video", "language")

    if role:
        role_enum = _resolve_role_enum(role)
        queryset = queryset.filter(video_role=role_enum)

    order_field = ORDERING_MAP.get(ordering, "position") if ordering else "position"
    queryset = queryset.order_by(order_field)

    return queryset


def get_product_video(channel_idx: str, sku: str, pk: int) -> ProductVideo:
    """
    Get a single product video.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
        ProductVideo.DoesNotExist: If not found
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)

    return ProductVideo.objects.select_related("video", "language").get(product=product, pk=pk)


@transaction.atomic
def create_product_video(
    channel_idx: str,
    sku: str,
    video_url: str,
    title: str | None = None,
    video_role: str = "unknown",
    language_iso2: str | None = None,
    position: int = 0,
) -> ProductVideo:
    """
    Create a video and link it to a product.

    The Video model auto-detects source (YouTube/Vimeo) from the URL.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
        ValueError: If role/language constraints violated
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    role_enum = _resolve_role_enum(video_role)
    language = _resolve_language(language_iso2)

    video = Video.objects.create(video_url=video_url, title=title, is_external=True)

    pv = ProductVideo.objects.create(
        product=product, video=video, video_role=role_enum, language=language, position=position
    )

    return ProductVideo.objects.select_related("video", "language").get(pk=pv.pk)


@transaction.atomic
def update_product_video(channel_idx: str, sku: str, pk: int, **fields: object) -> ProductVideo:
    """Update a product video assignment."""
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    pv = ProductVideo.objects.select_related("video", "language").get(product=product, pk=pk)

    if "video_role" in fields and fields["video_role"] is not None:
        pv.video_role = _resolve_role_enum(fields.pop("video_role"))

    if "language_iso2" in fields:
        lang_val = fields.pop("language_iso2")
        pv.language = _resolve_language(lang_val)

    if "title" in fields and fields["title"] is not None:
        pv.video.title = fields.pop("title")
        pv.video.save()

    for field, value in fields.items():
        if value is not None:
            setattr(pv, field, value)
    pv.save()

    return ProductVideo.objects.select_related("video", "language").get(pk=pv.pk)


@transaction.atomic
def delete_product_video(channel_idx: str, sku: str, pk: int) -> dict:
    """
    Delete a product video assignment and its Video object.

    Unlike pictures/files, videos are 1:1 with ProductVideo, so we delete both.
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    pv = ProductVideo.objects.select_related("video").get(product=product, pk=pk)
    video = pv.video
    pv.delete()
    _, deleted_detail = video.delete()
    result = {"ProductVideo": 1}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result
