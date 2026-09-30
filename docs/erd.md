---
title: "PIM: Database Diagrams"
description: "Auto-generated ER diagrams for the PIM module."
sidebar:
  badge:
    text: "Auto-gen"
    variant: "note"
---

:::caution[Auto-generated]
These diagrams are auto-generated from Django model introspection.
Do not edit. Run `make erd` in entirius-docker to regenerate.
:::

## Core Products

```d2 layout=elk
Product: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  real_product_id: int {constraint: foreign_key}
  shop_id: int {constraint: foreign_key}
  feature_set_id: int {constraint: foreign_key}
  product_class: int
  visibility: int
  magento_pk: int
  updated_at: timestamp
}

RealProduct: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  sku: varchar
  ean: varchar
  kind_of_product: int
  weight: decimal
  "width": decimal
  "height": decimal
  deep: decimal
}

ProductSimple: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  real_product_id: int {constraint: foreign_key}
  shop_id: int {constraint: foreign_key}
  feature_set_id: int {constraint: foreign_key}
  product_ptr_id: int {constraint: primary_key}
  product_class: int
  visibility: int
  magento_pk: int
}

ProductConfigurable: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  real_product_id: int {constraint: foreign_key}
  shop_id: int {constraint: foreign_key}
  feature_set_id: int {constraint: foreign_key}
  product_ptr_id: int {constraint: primary_key}
  product_class: int
  visibility: int
  magento_pk: int
}

ProductBundle: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  real_product_id: int {constraint: foreign_key}
  shop_id: int {constraint: foreign_key}
  feature_set_id: int {constraint: foreign_key}
  product_ptr_id: int {constraint: primary_key}
  product_class: int
  visibility: int
  magento_pk: int
}

ProductCustom: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  real_product_id: int {constraint: foreign_key}
  shop_id: int {constraint: foreign_key}
  feature_set_id: int {constraint: foreign_key}
  product_ptr_id: int {constraint: primary_key}
  customization_feature_set_id: int {constraint: foreign_key}
  source_product_id: int {constraint: foreign_key}
  product_class: int
}

Channel: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  idx: varchar {constraint: unique}
  name: varchar {constraint: unique}
  default_language_id: int {constraint: foreign_key}
  default_currency_id: int {constraint: foreign_key}
  is_default: bool
  inheritance_enabled: bool
  default_inheritance_flags: jsonb
}

Currency: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Currency (External: django_regional)"
}

FeatureSet: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "FeatureSet (See features-attributes diagram)"
}

Language: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Language (External: django_regional)"
}



Product.real_product_id -> RealProduct.id: {style.stroke: "#00ACC1"}

Product.shop_id -> Channel.id: {style.stroke: "#00ACC1"}

Product.feature_set_id -> FeatureSet.id: {style.stroke: "#484B57"}

ProductSimple.real_product_id -> RealProduct.id: {style.stroke: "#00ACC1"}

ProductSimple.shop_id -> Channel.id: {style.stroke: "#00ACC1"}

ProductSimple.feature_set_id -> FeatureSet.id: {style.stroke: "#484B57"}

ProductSimple.product_ptr_id -> Product.id: {style.stroke: "#00ACC1"}

ProductConfigurable.real_product_id -> RealProduct.id: {style.stroke: "#00ACC1"}

ProductConfigurable.shop_id -> Channel.id: {style.stroke: "#00ACC1"}

ProductConfigurable.feature_set_id -> FeatureSet.id: {style.stroke: "#484B57"}

ProductConfigurable.product_ptr_id -> Product.id: {style.stroke: "#00ACC1"}

ProductBundle.real_product_id -> RealProduct.id: {style.stroke: "#00ACC1"}

ProductBundle.shop_id -> Channel.id: {style.stroke: "#00ACC1"}

ProductBundle.feature_set_id -> FeatureSet.id: {style.stroke: "#484B57"}

ProductBundle.product_ptr_id -> Product.id: {style.stroke: "#00ACC1"}

ProductCustom.real_product_id -> RealProduct.id: {style.stroke: "#00ACC1"}

ProductCustom.shop_id -> Channel.id: {style.stroke: "#00ACC1"}

ProductCustom.feature_set_id -> FeatureSet.id: {style.stroke: "#484B57"}

ProductCustom.product_ptr_id -> Product.id: {style.stroke: "#00ACC1"}

ProductCustom.customization_feature_set_id -> FeatureSet.id: {style.stroke: "#484B57"}

ProductCustom.source_product_id -> Product.id: {style.stroke: "#00ACC1"}

Channel.default_language_id -> Language.id: {style.stroke: "#484B57"}

Channel.default_currency_id -> Currency.id: {style.stroke: "#484B57"}

Channel.id <-> Language.id: {style.stroke: "#484B57"}

Channel.id <-> Currency.id: {style.stroke: "#484B57"}
```

## Features & Attributes

```d2 layout=elk
Feature: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  idx: varchar {constraint: unique}
  magento_idx: varchar {constraint: unique}
  scope: int
  magento_pk: int
  name_t9n: jsonb
  desc: text
  is_required: bool
}

FeatureSet: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  idx: varchar {constraint: unique}
  name: varchar
  desc: text
  magento_idx: varchar
  magento_pk: int
  is_default: bool
}

FeatureInFeatureSet: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  feature_set_id: int {constraint: foreign_key}
  feature_id: int {constraint: foreign_key}
  attributes_group_id: int {constraint: foreign_key}
  position: int
  is_required: bool
}

Attribute: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  feature_id: int {constraint: foreign_key}
  group_id: int {constraint: foreign_key}
  idx: varchar
  extension: jsonb
  magento_idx: varchar
  magento_pk: int
  name_t9n: jsonb
}

AttributeModifier: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  real_product_id: int {constraint: foreign_key}
  feature_id: int {constraint: foreign_key}
  feature_modified_id: int {constraint: foreign_key}
  attribute_modified_id: int {constraint: foreign_key}
  attribute_coerced_id: int {constraint: foreign_key}
  source_id: float
}

AttributesGroup: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  idx: varchar {constraint: unique}
  name_t9n: jsonb
  desc: text
}

ProductAttribute: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  feature_id: int {constraint: foreign_key}
  attribute_id: int {constraint: foreign_key}
  value_bool: bool
  value_decimal: decimal
  value_datetime: timestamp
  overridden_langs: jsonb
}

ProductLinkToFeature: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  link_id: int {constraint: foreign_key}
  feature_id: int {constraint: foreign_key}
}

ProductAttributeImage: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  attribute_id: int {constraint: foreign_key}
  picture_id: int {constraint: foreign_key}
  color_hash: varchar
}

Picture: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Picture (See media diagram)"
}

Product: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Product (See core-products diagram)"
}

ProductLink: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "ProductLink (See pricing-links diagram)"
}

RealProduct: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "RealProduct (See core-products diagram)"
}



FeatureInFeatureSet.feature_set_id -> FeatureSet.id: {style.stroke: "#00ACC1"}

FeatureInFeatureSet.feature_id -> Feature.id: {style.stroke: "#00ACC1"}

FeatureInFeatureSet.attributes_group_id -> AttributesGroup.id: {style.stroke: "#00ACC1"}

Attribute.feature_id -> Feature.id: {style.stroke: "#00ACC1"}

Attribute.group_id -> AttributesGroup.id: {style.stroke: "#00ACC1"}

AttributeModifier.product_id -> Product.id: {style.stroke: "#484B57"}

AttributeModifier.real_product_id -> RealProduct.id: {style.stroke: "#484B57"}

AttributeModifier.feature_id -> Feature.id: {style.stroke: "#00ACC1"}

AttributeModifier.feature_modified_id -> Feature.id: {style.stroke: "#00ACC1"}

AttributeModifier.attribute_modified_id -> Attribute.id: {style.stroke: "#00ACC1"}

AttributeModifier.attribute_coerced_id -> Attribute.id: {style.stroke: "#00ACC1"}

AttributeModifier.id <-> Attribute.id: {style.stroke: "#00ACC1"}

AttributeModifier.id <-> AttributesGroup.id: {style.stroke: "#00ACC1"}

ProductAttribute.product_id -> Product.id: {style.stroke: "#484B57"}

ProductAttribute.feature_id -> Feature.id: {style.stroke: "#00ACC1"}

ProductAttribute.attribute_id -> Attribute.id: {style.stroke: "#00ACC1"}

ProductLinkToFeature.link_id -> ProductLink.id: {style.stroke: "#484B57"}

ProductLinkToFeature.feature_id -> Feature.id: {style.stroke: "#00ACC1"}

ProductAttributeImage.product_id -> Product.id: {style.stroke: "#484B57"}

ProductAttributeImage.attribute_id -> Attribute.id: {style.stroke: "#00ACC1"}

ProductAttributeImage.picture_id -> Picture.id: {style.stroke: "#484B57"}
```

## Categories

```d2 layout=elk
ProductCategory: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  shop_id: int {constraint: foreign_key}
  parent_category_id: int {constraint: foreign_key}
  idx: varchar
  external_id: varchar
  url_key_t9n: jsonb
  name_t9n: jsonb
  desc: text
}

ProductInCategory: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  category_id: int {constraint: foreign_key}
  position: int
  updated_at: timestamp
}

ProductCategoryPicture: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_category_id: int {constraint: foreign_key}
  picture_id: int {constraint: foreign_key}
  picture_role: int
  position: int
}

Channel: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Channel (See core-products diagram)"
}

Picture: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Picture (See media diagram)"
}

Product: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Product (See core-products diagram)"
}



ProductCategory.shop_id -> Channel.id: {style.stroke: "#484B57"}

ProductCategory.parent_category_id -> ProductCategory.id: {style.stroke: "#00ACC1"}

ProductInCategory.product_id -> Product.id: {style.stroke: "#484B57"}

ProductInCategory.category_id -> ProductCategory.id: {style.stroke: "#00ACC1"}

ProductCategoryPicture.product_category_id -> ProductCategory.id: {style.stroke: "#00ACC1"}

ProductCategoryPicture.picture_id -> Picture.id: {style.stroke: "#484B57"}
```

## Media

```d2 layout=elk
Picture: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  sha1: varchar {constraint: unique}
  image: varchar
  "width": int
  "height": int
  original_file_name: varchar
}

Thumb: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  sha1: varchar {constraint: unique}
  image: varchar
  "width": int
  "height": int
}

PictureThumb: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  picture_id: int {constraint: foreign_key}
  thumb_id: int {constraint: foreign_key}
  "width": int
  "height": int
  transform_method: varchar
  out_format: varchar
}

PictureDownloadUrl: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  picture_id: int {constraint: foreign_key}
  url: varchar {constraint: unique}
}

ProductPicture: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  picture_id: int {constraint: foreign_key}
  language_id: int {constraint: foreign_key}
  picture_role: int
  position: int
  alt_text_t9n: jsonb
  is_inherited: bool
}

AttributePicture: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  attribute_id: int {constraint: foreign_key}
  picture_id: int {constraint: foreign_key}
}

Video: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  title: varchar
  is_external: bool
  source: varchar
  video_url: varchar
}

ProductVideo: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  video_id: int {constraint: foreign_key}
  language_id: int {constraint: foreign_key}
  video_role: int
  position: int
  is_inherited: bool
}

ProductAttributeCustomImage: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  picture_id: int {constraint: foreign_key}
}

Attribute: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Attribute (See features-attributes diagram)"
}

Language: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Language (External: django_regional)"
}

Product: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Product (See core-products diagram)"
}



PictureThumb.picture_id -> Picture.id: {style.stroke: "#00ACC1"}

PictureThumb.thumb_id -> Thumb.id: {style.stroke: "#00ACC1"}

PictureDownloadUrl.picture_id -> Picture.id: {style.stroke: "#00ACC1"}

ProductPicture.product_id -> Product.id: {style.stroke: "#484B57"}

ProductPicture.picture_id -> Picture.id: {style.stroke: "#00ACC1"}

ProductPicture.language_id -> Language.id: {style.stroke: "#484B57"}

AttributePicture.attribute_id -> Attribute.id: {style.stroke: "#484B57"}

AttributePicture.picture_id -> Picture.id: {style.stroke: "#00ACC1"}

ProductVideo.product_id -> Product.id: {style.stroke: "#484B57"}

ProductVideo.video_id -> Video.id: {style.stroke: "#00ACC1"}

ProductVideo.language_id -> Language.id: {style.stroke: "#484B57"}

ProductAttributeCustomImage.product_id -> Product.id: {style.stroke: "#484B57"}

ProductAttributeCustomImage.picture_id -> Picture.id: {style.stroke: "#00ACC1"}

ProductAttributeCustomImage.id <-> Attribute.id: {style.stroke: "#484B57"}
```

## Files & Downloads

```d2 layout=elk
Files: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  file_category_id: int {constraint: foreign_key}
  sha1: varchar {constraint: unique}
  file: varchar
  original_file_name: varchar
  file_label: varchar
  file_label_t9n: jsonb
  weight: varchar
}

FilesCategory: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  name_t9n: jsonb
  code: varchar
}

FilesDownloadUrl: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  file_id: int {constraint: foreign_key}
  url: varchar {constraint: unique}
}

ProductFile: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  file_id: int {constraint: foreign_key}
  is_inherited: bool
}

Product: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Product (See core-products diagram)"
}



Files.file_category_id -> FilesCategory.id: {style.stroke: "#00ACC1"}

FilesDownloadUrl.file_id -> Files.id: {style.stroke: "#00ACC1"}

ProductFile.product_id -> Product.id: {style.stroke: "#484B57"}

ProductFile.file_id -> Files.id: {style.stroke: "#00ACC1"}
```

## Bundles & Configurable

```d2 layout=elk
BundleSection: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  idx: varchar {constraint: unique}
  name: jsonb
  desc: jsonb
  section_type: int
}

BundleLink: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_bundle_id: int {constraint: foreign_key}
  subproduct_id: int {constraint: foreign_key}
  section_id: int {constraint: foreign_key}
  quantity: int
  order: int
  can_change_quantity: bool
  is_default: bool
}

ConfigurableLink: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_configurable_id: int {constraint: foreign_key}
  subproduct_attribute_id: int {constraint: foreign_key}
  subproduct_id: int {constraint: foreign_key}
}

Product: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Product (See core-products diagram)"
}

ProductAttribute: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "ProductAttribute (See features-attributes diagram)"
}

ProductBundle: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  product_ptr_id: int {constraint: primary_key}
  label: "ProductBundle (See core-products diagram)"
}

ProductConfigurable: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  product_ptr_id: int {constraint: primary_key}
  label: "ProductConfigurable (See core-products diagram)"
}



BundleLink.product_bundle_id -> ProductBundle.product_ptr_id: {style.stroke: "#484B57"}

BundleLink.subproduct_id -> Product.id: {style.stroke: "#484B57"}

BundleLink.section_id -> BundleSection.id: {style.stroke: "#00ACC1"}

ConfigurableLink.product_configurable_id -> ProductConfigurable.product_ptr_id: {style.stroke: "#484B57"}

ConfigurableLink.subproduct_attribute_id -> ProductAttribute.id: {style.stroke: "#484B57"}

ConfigurableLink.subproduct_id -> Product.id: {style.stroke: "#484B57"}
```

## Pricing & Links

```d2 layout=elk
ProductPrice: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  currency_id: int {constraint: foreign_key}
  price_brutto: decimal
  special_price: decimal
  special_price_from: timestamp
  special_price_to: timestamp
}

ProductLink: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  linked_product_id: int {constraint: foreign_key}
  link_type_id: int {constraint: foreign_key}
  position: int
}

ProductLinkType: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  idx: varchar {constraint: unique}
  name_t9n: jsonb
  desc: text
  position: int
}

Currency: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Currency (External: django_regional)"
}

Product: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Product (See core-products diagram)"
}



ProductPrice.product_id -> Product.id: {style.stroke: "#484B57"}

ProductPrice.currency_id -> Currency.id: {style.stroke: "#484B57"}

ProductLink.product_id -> Product.id: {style.stroke: "#484B57"}

ProductLink.linked_product_id -> Product.id: {style.stroke: "#484B57"}

ProductLink.link_type_id -> ProductLinkType.id: {style.stroke: "#00ACC1"}
```

## Quality Gaps

```d2 layout=elk
GapDefinition: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  key: varchar {constraint: unique}
  check_key: varchar
  params: jsonb
  languages: jsonb
  channels: jsonb
  severity: varchar
  label_t9n: jsonb
}

GapFinding: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  definition_id: int {constraint: foreign_key}
  channel_idx: varchar
  language: varchar
  severity: varchar
  inherited: bool
  source_channel: varchar
}

GapExemption: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  product_id: int {constraint: foreign_key}
  definition_id: int {constraint: foreign_key}
  created_by_id: int {constraint: foreign_key}
  language: varchar
  reason: varchar
}

PimSettings: {
  shape: sql_table
  style.fill: "#00ACC1"
  style.stroke: "#12141A"
  style.font-color: "#EBEDF2"
  id: int {constraint: primary_key}
  matrix_signals_enabled: bool
  gaps_enabled: bool
  gaps_rules_changed_at: timestamp
  gaps_recomputed_at: timestamp
  gaps_skip_default_featureset: bool
}

Product: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "Product (See core-products diagram)"
}

User: {
  shape: sql_table
  style.fill: "#484B57"
  style.stroke: "#1A1C25"
  style.stroke-dash: 3
  style.font-color: "#9A9CAA"
  id: int {constraint: primary_key}
  label: "User (External: auth)"
}



GapFinding.product_id -> Product.id: {style.stroke: "#484B57"}

GapFinding.definition_id -> GapDefinition.id: {style.stroke: "#00ACC1"}

GapExemption.product_id -> Product.id: {style.stroke: "#484B57"}

GapExemption.definition_id -> GapDefinition.id: {style.stroke: "#00ACC1"}

GapExemption.created_by_id -> User.id: {style.stroke: "#484B57"}
```
