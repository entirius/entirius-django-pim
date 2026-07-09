"""
Request schemas for django-pim Admin API v2.

Contains Pydantic models for API request validation.
"""

from .attribute import AttributeReorderItem, AttributeReorderRequest, CreateAttributeRequest, UpdateAttributeRequest
from .attributes_group import CreateAttributesGroupRequest, UpdateAttributesGroupRequest
from .category import CategoryReorderItem, CategoryReorderRequest, CreateCategoryRequest, UpdateCategoryRequest
from .feature import CreateFeatureRequest, UpdateFeatureRequest
from .feature_in_feature_set import (
    BulkAddFeaturesRequest,
    BulkRemoveFeaturesRequest,
    FeatureInSetEntry,
    ReorderFeatureInSetEntry,
    ReorderFeaturesInSetRequest,
)
from .feature_set import CreateFeatureSetRequest, UpdateFeatureSetRequest
from .files_category import CreateFilesCategoryRequest, UpdateFilesCategoryRequest
from .gap_definition import CreateGapDefinitionRequest, UpdateGapDefinitionRequest
from .gap_exemption import CreateGapExemptionRequest
from .gap_settings import UpdateGapSettingsRequest
from .inheritance import (
    AddToChannelRequest,
    CopyAttributesRequest,
    CopyTranslationsRequest,
    ToggleLanguageOverrideRequest,
    ToggleMediaOverrideRequest,
)
from .product import BulkProductUpdateRequest, CreateProductRequest, ProductAttributeValueRequest, UpdateProductRequest
from .product_file import LinkFileRequest
from .product_in_category import ProductPositionItem, ProductPositionReorderRequest
from .product_link import CreateProductLinkRequest, UpdateProductLinkRequest
from .product_link_type import CreateProductLinkTypeRequest, UpdateProductLinkTypeRequest
from .product_picture import LinkPictureRequest, UpdateProductPictureRequest
from .product_video import CreateProductVideoRequest, UpdateProductVideoRequest

__all__ = [
    "CreateFeatureSetRequest",
    "UpdateFeatureSetRequest",
    "CreateFeatureRequest",
    "UpdateFeatureRequest",
    "CreateAttributeRequest",
    "UpdateAttributeRequest",
    "AttributeReorderItem",
    "AttributeReorderRequest",
    "CreateAttributesGroupRequest",
    "UpdateAttributesGroupRequest",
    "FeatureInSetEntry",
    "BulkAddFeaturesRequest",
    "BulkRemoveFeaturesRequest",
    "ReorderFeatureInSetEntry",
    "ReorderFeaturesInSetRequest",
    "CreateProductRequest",
    "UpdateProductRequest",
    "ProductAttributeValueRequest",
    "BulkProductUpdateRequest",
    "CreateCategoryRequest",
    "UpdateCategoryRequest",
    "CategoryReorderItem",
    "CategoryReorderRequest",
    "CreateProductLinkTypeRequest",
    "UpdateProductLinkTypeRequest",
    "CreateProductLinkRequest",
    "UpdateProductLinkRequest",
    "LinkPictureRequest",
    "UpdateProductPictureRequest",
    "CreateFilesCategoryRequest",
    "UpdateFilesCategoryRequest",
    "LinkFileRequest",
    "CreateProductVideoRequest",
    "UpdateProductVideoRequest",
    "CopyTranslationsRequest",
    "CopyAttributesRequest",
    "AddToChannelRequest",
    "ToggleLanguageOverrideRequest",
    "ToggleMediaOverrideRequest",
    "ProductPositionItem",
    "ProductPositionReorderRequest",
    "CreateGapDefinitionRequest",
    "UpdateGapDefinitionRequest",
    "CreateGapExemptionRequest",
    "UpdateGapSettingsRequest",
]
