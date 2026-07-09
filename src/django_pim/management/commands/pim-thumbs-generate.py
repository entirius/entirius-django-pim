# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand
from django.db.models import Q

from ... import settings
from ...models import Picture, Shop
from ...utils.pim_image_resizer import PimImageResizer


class Command(BaseCommand):
    help = "Generate thumbnails"

    def add_arguments(self, parser):
        Shop.objects.availability_table(print_out=True)
        parser.add_argument("shop_idx", type=str, help="Shop.idx")
        parser.add_argument("--clean", action="store_true", help="Clear all existing Thumbs before starting")
        parser.add_argument("--sku", type=str, help="Generate only for one product")

    @bi_django_command_decorator
    def handle(self, *args, **options):
        config = settings.THUMBS_CONFIG
        if config is None:
            self.stdout.write(self.style.ERROR("Image resizer config is invalid"))
            return False

        shop_idx = options["shop_idx"]
        shop = Shop.objects.get(idx=shop_idx)

        # products
        worker = PimImageResizer()
        sku = options["sku"]
        only_one_product_query = Q(products__product__real_product__sku=sku) if sku else Q()
        pictures_to_process = Picture.objects.filter(Q(products__product__shop=shop), only_one_product_query).distinct()
        print(f"Found {len(pictures_to_process)} pictures")
        if options["clean"]:
            worker.delete_thumbs(pictures_to_process)
        worker.resize_pictures(pictures_to_process, config)

        if sku:
            return

        # categories
        category_pictures_to_process = Picture.objects.filter(
            Q(product_categories__product_category__shop=shop)
        ).distinct()
        print(f"Found {len(category_pictures_to_process)} category pictures")
        if options["clean"]:
            worker.delete_thumbs(category_pictures_to_process)
        worker.resize_pictures(category_pictures_to_process, settings.CATEGORY_THUMBS_CONFIG)
