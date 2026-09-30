# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""URL routing for admin API endpoints."""

from django.urls import path

from .views import (
    AttributesGroupViewSet,
    AttributeViewSet,
    CategoryViewSet,
    ChannelViewSet,
    FeatureSetViewSet,
    FeatureViewSet,
    FilesCategoryViewSet,
    FileUpdateView,
    FileUploadView,
    GapDefinitionViewSet,
    GapExemptionViewSet,
    GapFindingViewSet,
    GapOpsViewSet,
    PictureUploadView,
    ProductFileViewSet,
    ProductInCategoryViewSet,
    ProductLinkTypeViewSet,
    ProductLinkViewSet,
    ProductPictureViewSet,
    ProductVideoViewSet,
    ProductViewSet,
)

urlpatterns = [
    # --- Channel endpoints (list-only, global) ---
    path("channels/", ChannelViewSet.as_view({"get": "list"}), name="channel-list"),
    # --- Quality gaps (etap-04) ---
    # Global: rule CRUD + recompute trigger + status. Literal-first prefixes — no clash with channel routes.
    path(
        "gap-definitions/",
        GapDefinitionViewSet.as_view({"get": "list", "post": "create"}),
        name="gapdefinition-list",
    ),
    path(
        "gap-definitions/<str:key>/",
        GapDefinitionViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="gapdefinition-detail",
    ),
    path("gaps/recompute/", GapOpsViewSet.as_view({"post": "recompute"}), name="gaps-recompute"),
    path("gaps/status/", GapOpsViewSet.as_view({"get": "status"}), name="gaps-status"),
    path(
        "gaps/settings/",
        GapOpsViewSet.as_view({"get": "get_settings", "patch": "patch_settings"}),
        name="gaps-settings",
    ),
    # Channel-scoped: bulk findings for a page of products.
    path(
        "<str:channel_idx>/gaps/findings/",
        GapFindingViewSet.as_view({"get": "list"}),
        name="gap-findings",
    ),
    # Channel-scoped: per-product rule mutes (deep mute, etap-13 gap-spawn).
    path(
        "<str:channel_idx>/gaps/exemptions/",
        GapExemptionViewSet.as_view({"get": "list", "post": "create"}),
        name="gap-exemptions",
    ),
    path(
        "<str:channel_idx>/gaps/exemptions/<int:pk>/",
        GapExemptionViewSet.as_view({"delete": "destroy"}),
        name="gap-exemption-detail",
    ),
    # --- Product endpoints (CRUD, channel-scoped) ---
    path("<str:channel_idx>/products/", ProductViewSet.as_view({"get": "list", "post": "create"}), name="product-list"),
    path(
        "<str:channel_idx>/products/bulk/", ProductViewSet.as_view({"post": "bulk_update"}), name="product-bulk-update"
    ),
    # NOTE: `product-detail` (`products/<path:sku>/`) is registered LAST among the product
    # routes (see end of this list). `<path:sku>` matches slashes, so a greedy detail match
    # would swallow `/pictures/`, `/links/` etc. — every product sub-route MUST precede it.
    path(
        "<str:channel_idx>/products/<path:sku>/copy-attributes/",
        ProductViewSet.as_view({"post": "copy_attributes_action"}),
        name="product-copy-attributes",
    ),
    # Backward-compatible alias
    path(
        "<str:channel_idx>/products/<path:sku>/copy-translations/",
        ProductViewSet.as_view({"post": "copy_attributes_action"}),
        name="product-copy-translations",
    ),
    path(
        "<str:channel_idx>/products/<path:sku>/add-to-channel/",
        ProductViewSet.as_view({"post": "add_to_channel"}),
        name="product-add-to-channel",
    ),
    path(
        "<str:channel_idx>/products/<path:sku>/toggle-override/",
        ProductViewSet.as_view({"post": "toggle_override"}),
        name="product-toggle-override",
    ),
    path(
        "<str:channel_idx>/products/<path:sku>/toggle-media-override/",
        ProductViewSet.as_view({"post": "toggle_media_override_action"}),
        name="product-toggle-media-override",
    ),
    # --- Category endpoints (CRUD, channel-scoped) ---
    path(
        "<str:channel_idx>/categories/",
        CategoryViewSet.as_view({"get": "list", "post": "create"}),
        name="category-list",
    ),
    path(
        "<str:channel_idx>/categories/reorder/", CategoryViewSet.as_view({"patch": "reorder"}), name="category-reorder"
    ),
    path(
        "<str:channel_idx>/categories/<str:idx>/",
        CategoryViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="category-detail",
    ),
    # --- Category products (positions) ---
    path(
        "<str:channel_idx>/categories/<str:idx>/products/",
        ProductInCategoryViewSet.as_view({"get": "list"}),
        name="category-products-list",
    ),
    path(
        "<str:channel_idx>/categories/<str:idx>/products/reorder/",
        ProductInCategoryViewSet.as_view({"patch": "reorder"}),
        name="category-products-reorder",
    ),
    # --- Feature endpoints (CRUD on global, read-only on channel-scoped) ---
    path("features/", FeatureViewSet.as_view({"get": "list", "post": "create"}), name="feature-list"),
    path(
        "features/<str:idx>/",
        FeatureViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="feature-detail",
    ),
    path("<str:channel_idx>/features/", FeatureViewSet.as_view({"get": "list"}), name="feature-list-shop"),
    path(
        "<str:channel_idx>/features/<str:idx>/", FeatureViewSet.as_view({"get": "retrieve"}), name="feature-detail-shop"
    ),
    # Feature nested attributes (read-only)
    path("features/<str:idx>/attributes/", FeatureViewSet.as_view({"get": "attributes"}), name="feature-attributes"),
    path(
        "<str:channel_idx>/features/<str:idx>/attributes/",
        FeatureViewSet.as_view({"get": "attributes"}),
        name="feature-attributes-shop",
    ),
    # --- FeatureSet endpoints (CRUD on global, read-only on channel-scoped) ---
    path("feature-sets/", FeatureSetViewSet.as_view({"get": "list", "post": "create"}), name="featureset-list"),
    path(
        "feature-sets/<str:idx>/",
        FeatureSetViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="featureset-detail",
    ),
    path(
        "feature-sets/<str:idx>/features/",
        FeatureSetViewSet.as_view({"get": "features", "post": "add_features", "delete": "remove_features"}),
        name="featureset-features",
    ),
    path(
        "feature-sets/<str:idx>/features/reorder/",
        FeatureSetViewSet.as_view({"patch": "reorder_features"}),
        name="featureset-features-reorder",
    ),
    path(
        "feature-sets/<str:idx>/features/<str:feature_idx>/",
        FeatureSetViewSet.as_view({"patch": "set_feature_required"}),
        name="featureset-feature-required",
    ),
    path(
        "feature-sets/<str:idx>/required-features/",
        FeatureSetViewSet.as_view({"get": "required_features"}),
        name="featureset-required-features",
    ),
    path("<str:channel_idx>/feature-sets/", FeatureSetViewSet.as_view({"get": "list"}), name="featureset-list-shop"),
    path(
        "<str:channel_idx>/feature-sets/<str:idx>/",
        FeatureSetViewSet.as_view({"get": "retrieve"}),
        name="featureset-detail-shop",
    ),
    path(
        "<str:channel_idx>/feature-sets/<str:idx>/features/",
        FeatureSetViewSet.as_view({"get": "features"}),
        name="featureset-features-shop",
    ),
    path(
        "<str:channel_idx>/feature-sets/<str:idx>/required-features/",
        FeatureSetViewSet.as_view({"get": "required_features"}),
        name="featureset-required-features-shop",
    ),
    # --- Attribute endpoints (CRUD, composite key: feature_idx + idx) ---
    path("attributes/", AttributeViewSet.as_view({"get": "list", "post": "create"}), name="attribute-list"),
    path("attributes/reorder/", AttributeViewSet.as_view({"patch": "reorder"}), name="attribute-reorder"),
    path(
        "attributes/<str:feature_idx>/<str:idx>/",
        AttributeViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="attribute-detail",
    ),
    # --- AttributesGroup endpoints (CRUD on global, read-only on channel-scoped) ---
    path(
        "attributes-groups/",
        AttributesGroupViewSet.as_view({"get": "list", "post": "create"}),
        name="attributesgroup-list",
    ),
    path(
        "attributes-groups/<str:idx>/",
        AttributesGroupViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="attributesgroup-detail",
    ),
    path(
        "<str:channel_idx>/attributes-groups/",
        AttributesGroupViewSet.as_view({"get": "list"}),
        name="attributesgroup-list-shop",
    ),
    path(
        "<str:channel_idx>/attributes-groups/<str:idx>/",
        AttributesGroupViewSet.as_view({"get": "retrieve"}),
        name="attributesgroup-detail-shop",
    ),
    # --- ProductLinkType endpoints (CRUD, global) ---
    path("link-types/", ProductLinkTypeViewSet.as_view({"get": "list", "post": "create"}), name="linktype-list"),
    path(
        "link-types/<str:idx>/",
        ProductLinkTypeViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="linktype-detail",
    ),
    # --- ProductLink endpoints (CRUD, channel-scoped, nested under product) ---
    path(
        "<str:channel_idx>/products/<path:sku>/links/",
        ProductLinkViewSet.as_view({"get": "list", "post": "create"}),
        name="productlink-list",
    ),
    path(
        "<str:channel_idx>/products/<path:sku>/links/<int:pk>/",
        ProductLinkViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="productlink-detail",
    ),
    # --- Picture upload (global) ---
    path("pictures/upload/", PictureUploadView.as_view(), name="picture-upload"),
    # --- ProductPicture endpoints (CRUD, channel-scoped, nested under product) ---
    path(
        "<str:channel_idx>/products/<path:sku>/pictures/",
        ProductPictureViewSet.as_view({"get": "list", "post": "create"}),
        name="productpicture-list",
    ),
    path(
        "<str:channel_idx>/products/<path:sku>/pictures/<int:pk>/",
        ProductPictureViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="productpicture-detail",
    ),
    # --- FilesCategory endpoints (CRUD, global) ---
    path(
        "files-categories/", FilesCategoryViewSet.as_view({"get": "list", "post": "create"}), name="filescategory-list"
    ),
    path(
        "files-categories/<str:code>/",
        FilesCategoryViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="filescategory-detail",
    ),
    # --- File upload (global) ---
    path("files/upload/", FileUploadView.as_view(), name="file-upload"),
    path("files/<int:pk>/", FileUpdateView.as_view(), name="file-update"),
    # --- ProductFile endpoints (list, create, delete; channel-scoped, nested under product) ---
    path(
        "<str:channel_idx>/products/<path:sku>/files/",
        ProductFileViewSet.as_view({"get": "list", "post": "create"}),
        name="productfile-list",
    ),
    path(
        "<str:channel_idx>/products/<path:sku>/files/<int:pk>/",
        ProductFileViewSet.as_view({"delete": "destroy"}),
        name="productfile-detail",
    ),
    # --- ProductVideo endpoints (CRUD, channel-scoped, nested under product) ---
    path(
        "<str:channel_idx>/products/<path:sku>/videos/",
        ProductVideoViewSet.as_view({"get": "list", "post": "create"}),
        name="productvideo-list",
    ),
    path(
        "<str:channel_idx>/products/<path:sku>/videos/<int:pk>/",
        ProductVideoViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="productvideo-detail",
    ),
    # --- Product detail (MUST be last: greedy <path:sku> would otherwise shadow the
    #     sub-routes above for slash-containing SKUs like "1C01/N") ---
    path(
        "<str:channel_idx>/products/<path:sku>/",
        ProductViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="product-detail",
    ),
]
