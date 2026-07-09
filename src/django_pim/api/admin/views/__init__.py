"""Admin API ViewSets for django-pim."""

from .attribute_views import AttributeViewSet
from .attributes_group_views import AttributesGroupViewSet
from .category_views import CategoryViewSet
from .channel_views import ChannelViewSet
from .feature_set_views import FeatureSetViewSet
from .feature_views import FeatureViewSet
from .files_category_views import FilesCategoryViewSet
from .gaps_views import GapDefinitionViewSet, GapExemptionViewSet, GapFindingViewSet, GapOpsViewSet
from .product_file_views import FileUpdateView, FileUploadView, ProductFileViewSet
from .product_in_category_views import ProductInCategoryViewSet
from .product_link_type_views import ProductLinkTypeViewSet
from .product_link_views import ProductLinkViewSet
from .product_picture_views import PictureUploadView, ProductPictureViewSet
from .product_video_views import ProductVideoViewSet
from .product_views import ProductViewSet

__all__ = [
    "AttributeViewSet",
    "AttributesGroupViewSet",
    "CategoryViewSet",
    "ChannelViewSet",
    "FeatureSetViewSet",
    "FeatureViewSet",
    "FilesCategoryViewSet",
    "GapDefinitionViewSet",
    "GapExemptionViewSet",
    "GapFindingViewSet",
    "GapOpsViewSet",
    "FileUpdateView",
    "FileUploadView",
    "PictureUploadView",
    "ProductFileViewSet",
    "ProductInCategoryViewSet",
    "ProductLinkTypeViewSet",
    "ProductLinkViewSet",
    "ProductPictureViewSet",
    "ProductVideoViewSet",
    "ProductViewSet",
]
