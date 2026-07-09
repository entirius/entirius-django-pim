# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django.core.cache import cache
from slugify import slugify

from ..models.product_category import ProductCategory

logger = logging.getLogger(__name__)


class CategoryManager:
    def get_categories_in_el_tree_format(parent_category=None):
        """
        [
            {
                id: 1,
                label: 'Level one 1',
                children: [
                  {
                    id: 4,
                    label: 'Level two 1-1',
                    children: [
                        {
                          id: 9,
                          label: 'Level three 1-1-1'
                        }, {
                          id: 10,
                          label: 'Level three 1-1-2'
                        }
                        ]
                    }
                ]
            }, ...
        ]
        """
        rv = []
        query = ProductCategory.objects
        if parent_category is None:
            query = query.filter(parent_category__isnull=True)
        else:
            query = query.filter(parent_category=parent_category)
        for category in query.order_by("name_en"):
            children = CategoryManager.get_categories_in_el_tree_format(parent_category=category)
            rv.append({"id": category.id, "label": category.get_name_pl, "children": children})
        return rv

    def get_categories_tree_as_list(parent_category=None):
        key = "cattree-%s" % parent_category
        rv = cache.get(key)
        if rv is None:
            rv = []
            query = ProductCategory.objects
            if parent_category is None:
                query = query.filter(parent_category__isnull=True)
            else:
                query = query.filter(parent_category=parent_category)
            for category in query.order_by("name_en"):
                children = CategoryManager.get_categories_tree_as_list(parent_category=category)
                all_children_ids = [category.id]
                for child in children:
                    all_children_ids = all_children_ids + child["children_ids"]
                rv.append(
                    {
                        "id": category.id,
                        "name": category.get_name_pl,
                        "children_ids": list(set(all_children_ids)),  # unikalne wartosci
                    }
                )
                # print('%s children: %s' % (category.get_name_pl, children))
                for child in children:
                    rv.append(
                        {
                            "id": child["id"],
                            "name": "%s | %s" % (category.get_name_pl, child["name"]),
                            "children_ids": child["children_ids"],
                        }
                    )
            ttl = 60 * 60 * 1  # 1h
            cache.set(key, rv, ttl)
        return rv

    def get_category_name(name_raw):
        pos = name_raw.find("|")
        if pos < 0:
            name_en = name_pl = name_raw
        else:
            name_en, name_pl = name_raw.split("|")
        name_en = name_en.strip()
        name_pl = name_pl.strip()
        if name_en == "" and name_pl == "":
            name_pl = name_en = "unknown"
        else:
            if name_en == "":
                name_en = name_pl
            elif name_pl == "":
                name_pl = name_en
        return (name_en, name_pl)

    def generate_idx(name):
        idx = name.strip()
        idx = idx.lower()
        idx = slugify(name)
        idx = ProductCategory.validate_idx(idx)
        return idx

    def get_category_from_tree(category_path=None, extra_separators=None):
        if category_path is None:
            return None
        separator = ">"
        if extra_separators is None:
            extra_separators = ["\\", "/"]

        for extra_separator in extra_separators:
            category_path = category_path.replace(extra_separator, separator)

        names = category_path.split(separator)
        parent_category = None
        product_category = None
        for name in names:
            name_en, name_pl = CategoryManager.get_category_name(name)
            idx = CategoryManager.generate_idx(name_pl)
            product_category, created = ProductCategory.objects.get_or_create(
                parent_category=parent_category, idx=idx, defaults={"name_t9n": {"pl": name_pl, "en": name_en}}
            )
            parent_category = product_category
        return product_category

    def get_categories_having_products():
        categories = ProductCategory.objects.filter().exclude(products=None)
        return categories

    def update_product_category(product_category, name_t9n=None, is_active=None):
        updated = []
        to_save = False
        if name_t9n is not None:
            orig = product_category.name_t9n.copy()
            product_category.name_t9n.update(name_t9n)
            if product_category.name_t9n != orig:
                updated.append("name_t9n")
                to_save = True
        if is_active is not None and product_category.is_active != is_active:
            product_category.is_active = is_active
            updated.append("is_active")
            to_save = True
        if to_save:
            product_category.save()
            logger.info("ProductCategory [%s] updated fields: (%s)", product_category.idx, ", ".join(updated))
