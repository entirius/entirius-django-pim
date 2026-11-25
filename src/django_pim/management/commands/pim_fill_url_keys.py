# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Fill the missing product ``url_key`` (the storefront opens a product page by it).

A key is ``slug(name)-slug(sku)`` per language that has a name, unique within the channel for that language
(``-2``, ``-3``… on collision). A key that is already set is never changed, so a second run finds nothing.
Dry-run by default.

Usage:
  python manage.py pim_fill_url_keys                       # preview, every channel
  python manage.py pim_fill_url_keys --channel default-europe
  python manage.py pim_fill_url_keys --apply               # write
"""

from django.core.management.base import BaseCommand, CommandError

from django_pim.models import Channel, Product
from django_pim.services import url_key_service
from django_pim.settings import SYSTEM_FEATURE_NAME_IDX


class Command(BaseCommand):
    help = "Fill missing product url_keys from name and SKU (dry-run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the keys (default: only print them)")
        parser.add_argument("--channel", help="Channel idx (default: every channel)")

    def handle(self, *args, **options):
        apply = options["apply"]
        products = Product.objects.filter(products_attributes__feature__idx=SYSTEM_FEATURE_NAME_IDX).distinct()
        if channel_idx := options["channel"]:
            if not Channel.objects.filter(idx=channel_idx).exists():
                raise CommandError(f"Channel '{channel_idx}' does not exist")
            products = products.filter(shop__idx=channel_idx)

        products_changed = keys_set = 0
        for product in products.select_related("shop", "real_product").order_by("pk").iterator():
            generated = url_key_service.fill_missing_url_key(product, apply=apply)
            for lang, key in sorted(generated.items()):
                self.stdout.write(f"{product.shop.idx}\t{product.sku}\t{lang}\t{key}")
            products_changed += bool(generated)
            keys_set += len(generated)

        verb = "Set" if apply else "Would set"
        self.stdout.write(f"{verb} {keys_set} url_key value(s) on {products_changed} product(s).")
        if not apply and keys_set:
            self.stdout.write("Dry run: nothing written. Add --apply to write.")
