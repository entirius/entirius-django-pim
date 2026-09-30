# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import bi_django_command_decorator
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from ... import settings
from ...models import Picture, Shop
from ...utils.pim_image_resizer import PimImageResizer, ResizeStats


class Command(BaseCommand):
    help = (
        "Generate thumbnails. Exits non-zero when it found no pictures, or every thumbnail it "
        "was asked to produce failed."
    )

    def add_arguments(self, parser):
        Shop.objects.availability_table(print_out=True)
        parser.add_argument("shop_idx", type=str, help="Shop.idx")
        parser.add_argument("--clean", action="store_true", help="Clear all existing Thumbs before starting")
        parser.add_argument("--sku", type=str, help="Generate only for one product")
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Only process pictures that lack at least one configured thumbnail",
        )

    def _run_job(self, label: str, pictures, config, options: dict) -> ResizeStats:
        worker = PimImageResizer()
        if options["clean"]:
            worker.delete_thumbs(pictures)
        found = list(pictures)
        todo = worker.pictures_missing_thumbs(found, config) if options["missing_only"] else found
        self.stdout.write(f"{label}: {len(found)} found; pictures to process: {len(todo)}")
        stats = worker.resize_pictures(todo, config)
        stats.pictures = len(found)
        return stats

    @bi_django_command_decorator
    def handle(self, *args, **options):
        config = settings.THUMBS_CONFIG
        if config is None:
            raise CommandError("Image resizer config is invalid (THUMBS_CONFIG is not set)")

        shop = Shop.objects.get(idx=options["shop_idx"])
        sku = options["sku"]
        only_one_product_query = Q(products__product__real_product__sku=sku) if sku else Q()
        jobs = [
            (
                "Product pictures",
                Picture.objects.filter(Q(products__product__shop=shop), only_one_product_query).distinct(),
                config,
            )
        ]
        if not sku and settings.CATEGORY_THUMBS_CONFIG is not None:
            category_pictures = Picture.objects.filter(Q(product_categories__product_category__shop=shop)).distinct()
            jobs.append(("Category pictures", category_pictures, settings.CATEGORY_THUMBS_CONFIG))

        total = ResizeStats()
        for label, pictures, job_config in jobs:
            total += self._run_job(label, pictures, job_config, options)
        self._report(total, options)

    def _report(self, total: ResizeStats, options: dict) -> None:
        summary = (
            f"Thumbnails: generated {total.generated}, already present {total.existing}, "
            f"failed {total.failed} (pictures found: {total.pictures})"
        )
        if total.pictures == 0:
            raise CommandError(f"No pictures found for channel '{options['shop_idx']}'. {summary}")
        if total.failed and not (total.generated or total.existing):
            raise CommandError(f"Nothing was generated. {summary}")
        if options["missing_only"] and not (total.generated or total.failed):
            self.stdout.write(f"Nothing missing - every configured thumbnail exists. {summary}")
            return
        self.stdout.write(summary)
