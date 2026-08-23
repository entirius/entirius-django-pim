"""
Response schemas for django-pim APIs.

Contains Pydantic models for API responses.
"""

from .attribute import AttributeListResponse, AttributeResponse
from .attributes_group import AttributesGroupListResponse, AttributesGroupResponse
from .category import CategoryDetailResponse, CategoryListResponse, CategoryResponse
from .feature import FeatureListResponse, FeatureResponse
from .feature_set import FeatureInSetResponse, FeatureSetListResponse, FeatureSetResponse, FeaturesInSetListResponse
from .files_category import FilesCategoryListResponse, FilesCategoryResponse
from .gap import (
    GapDefinitionListResponse,
    GapDefinitionResponse,
    GapExemptionListResponse,
    GapExemptionResponse,
    GapFindingResponse,
    GapFindingsBulkResponse,
    GapRecomputeResponse,
    GapSettingsResponse,
    GapStatusResponse,
)
from .lookup import LookupBasicResponse, LookupReasonResponse, PossibleDuplicateResponse
from .product import (
    ProductAttributeValueResponse,
    ProductCategoryBriefResponse,
    ProductDetailResponse,
    ProductListResponse,
    ProductResponse,
)
from .product_file import FileResponse, ProductFileListResponse, ProductFileResponse
from .product_in_category import ProductInCategoryListResponse, ProductInCategoryResponse
from .product_link import LinkedProductBriefResponse, ProductLinkListResponse, ProductLinkResponse
from .product_link_type import ProductLinkTypeListResponse, ProductLinkTypeResponse
from .product_picture import PictureResponse, ProductPictureListResponse, ProductPictureResponse
from .product_video import ProductVideoListResponse, ProductVideoResponse, VideoResponse

__all__ = [
    "ProductResponse",
    "ProductListResponse",
    "ProductDetailResponse",
    "ProductAttributeValueResponse",
    "ProductCategoryBriefResponse",
    "PossibleDuplicateResponse",
    "LookupReasonResponse",
    "LookupBasicResponse",
    "CategoryResponse",
    "CategoryListResponse",
    "CategoryDetailResponse",
    "FeatureResponse",
    "FeatureListResponse",
    "FeatureSetResponse",
    "FeatureSetListResponse",
    "FeatureInSetResponse",
    "FeaturesInSetListResponse",
    "AttributeResponse",
    "AttributeListResponse",
    "AttributesGroupResponse",
    "AttributesGroupListResponse",
    "ProductLinkTypeResponse",
    "ProductLinkTypeListResponse",
    "LinkedProductBriefResponse",
    "ProductLinkResponse",
    "ProductLinkListResponse",
    "PictureResponse",
    "ProductPictureResponse",
    "ProductPictureListResponse",
    "FilesCategoryResponse",
    "FilesCategoryListResponse",
    "FileResponse",
    "ProductFileResponse",
    "ProductFileListResponse",
    "VideoResponse",
    "ProductVideoResponse",
    "ProductVideoListResponse",
    "ProductInCategoryResponse",
    "ProductInCategoryListResponse",
    "GapDefinitionResponse",
    "GapDefinitionListResponse",
    "GapExemptionResponse",
    "GapExemptionListResponse",
    "GapFindingResponse",
    "GapFindingsBulkResponse",
    "GapRecomputeResponse",
    "GapSettingsResponse",
    "GapStatusResponse",
]
