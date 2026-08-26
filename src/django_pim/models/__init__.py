from django_pim.models.product_file import ProductFile

from .attribute import Attribute, AttributeModifier, AttributeModifierTypeEnum
from .attribute_picture import AttributePicture
from .attributes_group import AttributesGroup
from .channel import Channel, Shop
from .feature import (
    Feature,
    FeatureScope,
    FeatureScopeEnum,
    FeatureType,
    FeatureTypeEnum,
    FilterType,
    FilterTypeEnum,
    FrontendInputType,
    FrontendInputTypeEnum,
)
from .feature_set import FeatureInFeatureSet, FeatureSet
from .files import FileRole, FileRoleEnum, Files
from .files_category import FilesCategory
from .files_download_url import FilesDownloadUrl
from .gap_definition import GapCheck, GapDefinition, GapSeverity
from .gap_exemption import GapExemption
from .gap_finding import GapFinding
from .picture import Picture
from .picture_download_url import PictureDownloadUrl
from .picture_thumb import PictureThumb
from .pim_settings import PimSettings
from .product import Product, ProductClass, ProductClassEnum, ProductVisibility, ProductVisibilityEnum
from .product_attribute import ProductAttribute
from .product_attribute_image import ProductAttributeImage
from .product_bundle import BundleLink, BundleSection, ProductBundle
from .product_category import ProductCategory
from .product_category_picture import ProductCategoryPicture
from .product_configurable import *
from .product_custom import ProductAttributeCustomImage, ProductCustom
from .product_in_category import ProductInCategory
from .product_link_to_feature import ProductLinkToFeature
from .product_link_type import ProductLinkType
from .product_links import ProductLink, ProductLinkTypeChoices, ProductLinkTypeEnum
from .product_picture import PictureRole, PictureRoleEnum, ProductPicture
from .product_price import ProductPrice
from .product_simple import *
from .product_variant_group import ProductVariantGroup, ProductVariantGroupProduct
from .product_video import ProductVideo, VideoRole, VideoRoleEnum
from .real_product import KindOfProductClass, KindOfProductEnum, RealProduct, normalize_sku, validate_ean, validate_sku
from .thumb import Thumb
from .video import Video, VideoSource
