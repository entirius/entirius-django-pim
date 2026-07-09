"""
Admin API endpoints for django-pim.

Contains DRF ViewSets for administrative operations.
"""

from .views import (
    AttributesGroupViewSet,
    AttributeViewSet,
    CategoryViewSet,
    FeatureSetViewSet,
    FeatureViewSet,
    ProductViewSet,
)

__all__ = [
    "ProductViewSet",
    "CategoryViewSet",
    "FeatureViewSet",
    "FeatureSetViewSet",
    "AttributeViewSet",
    "AttributesGroupViewSet",
]
