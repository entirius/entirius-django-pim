# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.apps import AppConfig


class DjangoPimConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_pim"
    verbose_name = "Product Information Management"
    is_volkanos = True
    # Copied 1:1 from entirius-django-access cf538d2 catalogue defaults;
    # the access defaults stay until this module's release.
    access_areas = [
        {"key": "pim.products", "label": "Products and media"},
        {"key": "pim.categories", "label": "Categories and positions"},
        {"key": "pim.schema", "label": "Features, attributes, sets and link types"},
        {"key": "pim.quality", "label": "Quality gaps"},
        {
            "key": "pim.product_delete",
            "label": "Delete products (SKU)",
            "levels": ("write",),
            "sensitive": ("destructive",),
        },
    ]
    # Every admin view carries its access_area; no route needs a path rule.
    access_route_rules = []

    def ready(self):
        from django_pim.signals import handlers  # noqa: F401
