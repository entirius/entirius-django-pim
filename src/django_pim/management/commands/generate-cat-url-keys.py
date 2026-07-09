# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.core.management.base import BaseCommand
from service_management.models import Shop

from ...utils.pim_cat_url_generator import PimCategoryGenerator


class Command(BaseCommand):
    def add_arguments(self, parser):
        Shop.objects.availability_table(print_out=True)
        parser.add_argument("shop_idx_path", type=str)
        parser.add_argument("tree_depth_to_skip", type=int)

    def handle(self, *args, **options):
        shop_idx_path = options["shop_idx_path"]
        tree_depth_to_skip = options["tree_depth_to_skip"]

        worker = PimCategoryGenerator()
        worker.generate_url_key(shop_idx_path, tree_depth_to_skip)
