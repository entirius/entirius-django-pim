# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from pim.models import ProductCategory


class PimCategoryGenerator:
    def __init__(self):
        super().__init__()

    def generate_url_key(self, shop_idx_path, tree_depth_to_skip):
        shop_idx = shop_idx_path.split(".")[-1]
        categories = ProductCategory.objects.filter(shop__idx=shop_idx, tree_deep__gt=tree_depth_to_skip).order_by(
            "tree_deep"
        )
        for category in categories:
            for lang in category.url_key_t9n:
                url_key = ""
                if category.parent_category is None:
                    continue
                parent_url_key = category.parent_category.url_key_t9n[lang]
                if category.url_key_t9n[lang].startswith(parent_url_key):
                    continue
                url_key = parent_url_key + "-" + category.url_key_t9n[lang]
                category.url_key_t9n[lang] = url_key
                category.save()
