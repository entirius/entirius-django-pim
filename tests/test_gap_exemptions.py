# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gap exemptions — deep mute (etap-13 gap-spawn).

Detection-level behaviour (an exempted pair never produces a finding), the immediate
re-detect on create/delete (incl. the silent rollup), and service validation. AAA.
"""

import pytest
from django.core.exceptions import ObjectDoesNotExist

from django_pim import models
from django_pim.models import FeatureScopeEnum, FeatureTypeEnum
from django_pim.models.gap_definition import GapCheck, GapSeverity
from django_pim.services import gap_detection_service as svc
from django_pim.services import gap_exemption_service
from tests.factories import (
    ChannelFactory,
    CurrencyFactory,
    FeatureFactory,
    FeatureSetFactory,
    GapDefinitionFactory,
    GapExemptionFactory,
    LanguageFactory,
    ProductFactory,
    RealProductFactory,
)

pytestmark = pytest.mark.django_db


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def lang_en(db):
    return LanguageFactory(iso2="EN", iso3="ENG")


@pytest.fixture
def channel(db, lang_en):
    return ChannelFactory(idx="ch-main", default_language=lang_en, default_currency=CurrencyFactory(iso3="EUR"))


@pytest.fixture
def description_feature(db):
    return FeatureFactory(idx="description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)


@pytest.fixture
def description_rule(db, description_feature):
    return GapDefinitionFactory(
        key="d",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )


@pytest.fixture
def product(channel):
    return ProductFactory(shop=channel, feature_set=FeatureSetFactory(), real_product=RealProductFactory())


def _findings(product):
    return models.GapFinding.objects.filter(product=product)


# --- detection skip -----------------------------------------------------------


def test_exempted_pair_produces_no_finding(product, description_rule):
    GapExemptionFactory(product=product, definition=description_rule, language="en")

    svc.detect_for_product(product)

    assert _findings(product).count() == 0
    product.refresh_from_db()
    assert product.gap_count == 0
    assert product.gap_evaluated_at is not None  # still evaluated — just muted


def test_null_language_mutes_all_languages(product, description_rule):
    GapExemptionFactory(product=product, definition=description_rule, language=None)

    svc.detect_for_product(product)

    assert _findings(product).count() == 0


def test_null_language_mutes_language_neutral_check(product):
    rule = GapDefinitionFactory(key="pic", check_key=GapCheck.PICTURE_PRESENT, severity=GapSeverity.WARNING, params={})
    GapExemptionFactory(product=product, definition=rule, language=None)

    svc.detect_for_product(product)

    assert _findings(product).count() == 0


def test_other_language_stays_flagged(product, description_rule):
    # Mute a language the channel does not even serve via the factory (direct row) —
    # the served language must keep its finding.
    models.GapExemption.objects.create(product=product, definition=description_rule, language="de")

    svc.detect_for_product(product)

    assert _findings(product).filter(language="en").count() == 1


def test_other_rule_stays_flagged(product, description_rule):
    other = GapDefinitionFactory(key="pic", check_key=GapCheck.PICTURE_PRESENT, severity=GapSeverity.WARNING, params={})
    GapExemptionFactory(product=product, definition=other, language=None)

    svc.detect_for_product(product)

    assert _findings(product).filter(definition=description_rule).count() == 1
    assert _findings(product).filter(definition=other).count() == 0


# --- service create/delete ----------------------------------------------------


def test_create_exemption_removes_finding_immediately(product, description_rule):
    svc.detect_for_product(product)
    assert _findings(product).count() == 1
    sku = product.real_product.sku

    exemption = gap_exemption_service.create_exemption(
        channel_idx="ch-main", sku=sku, definition_key="d", language="en", reason="genuinely fine"
    )

    assert exemption.language == "en"
    assert _findings(product).count() == 0
    product.refresh_from_db()
    assert product.gap_count == 0
    assert product.gap_worst_severity is None


def test_delete_exemption_restores_finding(product, description_rule):
    sku = product.real_product.sku
    exemption = gap_exemption_service.create_exemption(channel_idx="ch-main", sku=sku, definition_key="d")
    assert _findings(product).count() == 0

    gap_exemption_service.delete_exemption(channel_idx="ch-main", exemption_id=exemption.pk)

    assert _findings(product).count() == 1
    product.refresh_from_db()
    assert product.gap_count == 1


def test_create_uppercase_language_is_normalised(product, description_rule):
    exemption = gap_exemption_service.create_exemption(
        channel_idx="ch-main", sku=product.real_product.sku, definition_key="d", language="EN"
    )
    assert exemption.language == "en"


def test_create_rejects_unserved_language(product, description_rule):
    with pytest.raises(ValueError, match="not served"):
        gap_exemption_service.create_exemption(
            channel_idx="ch-main", sku=product.real_product.sku, definition_key="d", language="de"
        )


def test_create_rejects_duplicate(product, description_rule):
    gap_exemption_service.create_exemption(channel_idx="ch-main", sku=product.real_product.sku, definition_key="d")
    with pytest.raises(ValueError, match="already exists"):
        gap_exemption_service.create_exemption(channel_idx="ch-main", sku=product.real_product.sku, definition_key="d")


def test_create_unknown_definition_raises_does_not_exist(product):
    with pytest.raises(ObjectDoesNotExist):
        gap_exemption_service.create_exemption(
            channel_idx="ch-main", sku=product.real_product.sku, definition_key="nope"
        )


def test_create_unknown_sku_raises_does_not_exist(channel, description_rule):
    with pytest.raises(ObjectDoesNotExist):
        gap_exemption_service.create_exemption(channel_idx="ch-main", sku="no-such-sku", definition_key="d")


def test_delete_cross_channel_is_hidden(product, description_rule, lang_en):
    other_channel = ChannelFactory(
        idx="ch-other", default_language=lang_en, default_currency=CurrencyFactory(iso3="EUR")
    )
    exemption = GapExemptionFactory(product=product, definition=description_rule)

    with pytest.raises(ObjectDoesNotExist):
        gap_exemption_service.delete_exemption(channel_idx=other_channel.idx, exemption_id=exemption.pk)
    assert models.GapExemption.objects.filter(pk=exemption.pk).exists()


def test_list_exemptions_newest_first(product, description_rule):
    first = GapExemptionFactory(product=product, definition=description_rule, language="en")
    other_rule = GapDefinitionFactory(key="pic", check_key=GapCheck.PICTURE_PRESENT, params={})
    second = GapExemptionFactory(product=product, definition=other_rule)

    result = gap_exemption_service.list_exemptions(channel_idx="ch-main", sku=product.real_product.sku)

    assert [e.pk for e in result] == [second.pk, first.pk]
