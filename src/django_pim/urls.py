# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Main URL configuration for django-pim module.

This file is included in the service's main urls.py.
"""

from django.urls import include, path

from . import settings
from .views import api_viewer

app_name = "django_pim"

# Legacy API viewer URLs (keep for backward compatibility)
api_viewer_paths = [
    path("categories/", api_viewer.view_category, name="admin-category-list"),
    path("categories/<str:idx>/", api_viewer.view_category, name="admin-category-detail"),
    path("feature-sets/", api_viewer.view_feature_sets, name="admin-feature-set-list"),
    path("feature-sets/<str:idx>/", api_viewer.view_feature_sets, name="admin-feature-set-detail"),
    path("features/", api_viewer.view_features, name="admin-feature-list"),
    path("features/<str:idx>/", api_viewer.view_features, name="admin-feature-detail"),
    path("features/<str:idx>/attributes/", api_viewer.view_feature_attributes, name="features-attrs"),
    path(
        "features/<str:idx>/attributes/<str:attr_idx>/", api_viewer.view_feature_attribute, name="features-attrs-detail"
    ),
    path(
        "features/<str:idx>/attributes/<str:attr_idx>/extension/",
        api_viewer.view_attribute_extension,
        name="features-attrs-update",
    ),
    path("products/", api_viewer.view_products, name="admin-product-list"),
    path("products/<path:sku>/", api_viewer.view_products, name="admin-product-detail"),
]

urlpatterns = [
    # v2 Admin API (canonical URL — DRF + Pydantic + drf-spectacular)
    path("api/pim/v2/admin/", include("django_pim.api.admin.urls")),
    # Legacy admin URL (backward compatibility, same views)
    path("api/pim/admin/", include("django_pim.api.admin.urls")),
    # Legacy API viewer (backward compatibility)
    path(f"{settings.VIEWER_BASE_URL}/pim/<str:version>/<str:shop_idx>/", include(api_viewer_paths)),
]
