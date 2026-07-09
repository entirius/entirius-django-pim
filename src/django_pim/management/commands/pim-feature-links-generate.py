# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.core.management.base import BaseCommand
from service_management.models import BusinessUnit, Shop

from ...models import Feature, Product
from ...models.enums import ProductClass
from ...utils.pim_product_linker import PimProductLinker


class Command(BaseCommand):
    help = "Generate product links grouped by feature"

    def add_arguments(self, parser):
        Shop.objects.availability_table(print_out=True)
        (parser.add_argument("idx_path", type=str, help="Idx path of the format <businees_unit_idx>.<shop_idx>"))
        (parser.add_argument("link_by_feature_idx", type=str, help="Idx of the feature to group products by"))
        (parser.add_argument("link_feature_idx", type=str, help="Idx of the feature that should be assigned to links"))
        (parser.add_argument("--clear", type=bool, help="If true, deletes all navigation links before running"))

    def handle(self, *args, **options):
        idx_path = options["idx_path"]
        bu_idx, shop_idx = idx_path.split(".")
        bu = BusinessUnit.objects.get(idx=bu_idx)
        shop = Shop.objects.get(business_unit=bu, idx=shop_idx)
        link_by_feature = Feature.objects.get(business_unit=bu, idx=options["link_by_feature_idx"])
        link_feature = Feature.objects.get(business_unit=bu, idx=options["link_feature_idx"])
        worker = PimProductLinker()
        product_cls = ProductClass.enumClass.ProductConfigurable
        products_to_process = Product.objects.filter(shop=shop, product_class=product_cls)
        try:
            clear_existing = options.get("--clear", False)
            worker.link_by_feature(products_to_process, link_by_feature, link_feature, clear_existing=clear_existing)
            self.stdout.write(self.style.SUCCESS("Done"))
        except Exception as e:
            self.stdout.write(self.style.ERROR("Error"))
            self.stdout.write(self.style.ERROR(str(e)))
