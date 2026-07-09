# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import factory
from django_regional import models as regional_models

from django_pim import models


class LanguageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = regional_models.Language
        django_get_or_create = ("iso2",)

    iso2 = "PL"


class CurrencyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = regional_models.Currency
        django_get_or_create = ("iso3",)

    iso3 = "PLN"


class ChannelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Channel
        django_get_or_create = ("idx",)

    idx = factory.Sequence(lambda n: f"test-channel-{n}")
    name = factory.LazyAttribute(lambda o: f"Test Channel {o.idx}")
    default_language = factory.SubFactory(LanguageFactory)
    default_currency = factory.SubFactory(CurrencyFactory)


# Backward-compatible alias
ShopFactory = ChannelFactory


class FeatureSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FeatureSet

    idx = factory.Sequence(lambda x: f"test-feature-set-{x}")
    name = factory.Sequence(lambda x: f"Test Feature Set {x}")


class FeatureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Feature

    idx = factory.Sequence(lambda x: f"test-feature-{x}")


class AttributeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Attribute

    idx = factory.Sequence(lambda x: f"test-attribute-{x}")
    name_t9n = factory.LazyFunction(lambda: {"en": "Test Attribute"})


class RealProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.RealProduct

    sku = factory.Sequence(lambda x: f"test-sku-{x}")


class ProductCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductCategory

    idx = factory.Sequence(lambda x: f"test-category-{x}")
    shop = factory.SubFactory(ShopFactory)


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Product

    shop = factory.SubFactory(ShopFactory)
    feature_set = factory.SubFactory(FeatureSetFactory)
    real_product = factory.SubFactory(RealProductFactory)


class FeatureInFeatureSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FeatureInFeatureSet

    feature_set = factory.SubFactory(FeatureSetFactory)
    feature = factory.SubFactory(FeatureFactory)
    position = 500


class AttributesGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.AttributesGroup

    idx = factory.Sequence(lambda x: f"test-group-{x}")
    name_t9n = factory.LazyFunction(lambda: {"en": "Test Group"})


class ProductLinkTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductLinkType
        django_get_or_create = ("idx",)

    idx = factory.Sequence(lambda x: f"test-link-type-{x}")
    name_t9n = factory.LazyFunction(lambda: {"en": "Test Link Type"})
    position = 0


class ProductLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductLink

    product = factory.SubFactory(ProductFactory)
    linked_product = factory.SubFactory(ProductFactory)
    link_type = factory.SubFactory(ProductLinkTypeFactory)
    position = 1


class FilesCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FilesCategory

    code = factory.Sequence(lambda x: f"test-category-{x}")
    name_t9n = factory.LazyFunction(lambda: {"en": "Test File Category"})


class ProductInCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductInCategory

    product = factory.SubFactory(ProductFactory)
    category = factory.SubFactory(ProductCategoryFactory)
    position = 0


class GapDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.GapDefinition
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda x: f"test-gap-{x}")
    check_key = models.GapCheck.FEATURE_PRESENT
    severity = models.GapSeverity.CRITICAL
    params = factory.LazyFunction(lambda: {"feature_idx": "description"})
    label_t9n = factory.LazyFunction(lambda: {"en": "Missing"})


class GapFindingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.GapFinding

    product = factory.SubFactory(ProductFactory)
    definition = factory.SubFactory(GapDefinitionFactory)
    channel_idx = factory.LazyAttribute(lambda o: o.product.shop.idx)
    severity = factory.LazyAttribute(lambda o: o.definition.severity)
    language = "pl"


class GapExemptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.GapExemption

    product = factory.SubFactory(ProductFactory)
    definition = factory.SubFactory(GapDefinitionFactory)
    language = None


class ProductAttributeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProductAttribute
