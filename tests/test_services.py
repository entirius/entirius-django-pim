# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gap detection service + check registry (etap-02).

One test per correctness rule from the plan, plus idempotency, silent rollup, and the
params allowlist. AAA, isolated, no shared state.
"""

import io
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PILImage

from django_pim import models
from django_pim.models import FeatureScopeEnum, FeatureTypeEnum, PictureRoleEnum, ProductAttribute, ProductPicture
from django_pim.models.gap_definition import GapCheck, GapSeverity
from django_pim.services import gap_check_registry as registry
from django_pim.services import gap_detection_service as svc
from django_pim.services.product_picture_service import upload_picture
from tests.factories import (
    ChannelFactory,
    CurrencyFactory,
    FeatureFactory,
    FeatureInFeatureSetFactory,
    FeatureSetFactory,
    GapDefinitionFactory,
    LanguageFactory,
    ProductCategoryFactory,
    ProductFactory,
    ProductInCategoryFactory,
    RealProductFactory,
)

pytestmark = pytest.mark.django_db


# --- helpers -----------------------------------------------------------------


def _make_picture(color: str = "red"):
    buf = io.BytesIO()
    PILImage.new("RGB", (10, 10), color=color).save(buf, format="PNG")
    buf.seek(0)
    return upload_picture(SimpleUploadedFile("t.png", buf.read(), content_type="image/png"))


def _product(channel, feature_set=None):
    return ProductFactory(
        shop=channel, feature_set=feature_set or FeatureSetFactory(), real_product=RealProductFactory()
    )


def _findings(product):
    return models.GapFinding.objects.filter(product=product)


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def lang_en(db):
    return LanguageFactory(iso2="EN", iso3="ENG")


@pytest.fixture
def lang_pl(db):
    return LanguageFactory(iso2="PL", iso3="POL")


@pytest.fixture
def currency(db):
    return CurrencyFactory(iso3="EUR")


@pytest.fixture
def channel(db, lang_en, currency):
    return ChannelFactory(idx="ch-main", default_language=lang_en, default_currency=currency)


@pytest.fixture
def description_feature(db):
    """SYSTEM scope — applies even when not in the product's FeatureSet."""
    return FeatureFactory(idx="description", feature_type=FeatureTypeEnum.TEXT_T9N, scope=FeatureScopeEnum.SYSTEM)


# --- feature_present ----------------------------------------------------------


def test_feature_present_missing_creates_finding(channel, description_feature):
    product = _product(channel)
    GapDefinitionFactory(
        key="d",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )

    svc.detect_for_product(product)

    finding = _findings(product).get()
    assert finding.language == "en"
    assert finding.severity == GapSeverity.CRITICAL
    assert finding.inherited is False
    product.refresh_from_db()
    assert product.gap_count == 1
    assert product.gap_worst_severity == GapSeverity.CRITICAL
    assert product.gap_evaluated_at is not None


def test_feature_present_filled_no_finding(channel, description_feature):
    product = _product(channel)
    ProductAttribute.objects.create(
        product=product, feature=description_feature, value_txt_t9n={"en": "A real description"}
    )
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0
    product.refresh_from_db()
    assert product.gap_count == 0
    assert product.gap_evaluated_at is not None  # evaluated and genuinely OK


def test_empty_t9n_row_still_counts_as_gap(channel, description_feature):
    product = _product(channel)
    ProductAttribute.objects.create(product=product, feature=description_feature, value_txt_t9n={})  # row exists, empty
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 1


# --- feature_min_length -------------------------------------------------------


def test_feature_min_length_short_then_long(channel, description_feature):
    product = _product(channel)
    pa = ProductAttribute.objects.create(product=product, feature=description_feature, value_txt_t9n={"en": "abc"})
    GapDefinitionFactory(
        key="ml",
        check_key=GapCheck.FEATURE_MIN_LENGTH,
        severity=GapSeverity.WARNING,
        params={"feature_idx": "description", "min_length": 10},
    )

    svc.detect_for_product(product)
    assert _findings(product).count() == 1

    pa.value_txt_t9n = {"en": "this is long enough"}
    pa.save()
    svc.detect_for_product(product)
    assert _findings(product).count() == 0


# --- picture_present (language-neutral) --------------------------------------


def test_picture_present_zero_is_neutral_finding(channel):
    product = _product(channel)
    GapDefinitionFactory(key="pic", check_key=GapCheck.PICTURE_PRESENT, severity=GapSeverity.WARNING, params={})

    svc.detect_for_product(product)

    finding = _findings(product).get()
    assert finding.language is None  # one neutral finding, not one per channel language

    ProductPicture.objects.create(
        product=product, picture=_make_picture(), picture_role=PictureRoleEnum.MAIN, position=0
    )
    svc.detect_for_product(product)
    assert _findings(product).count() == 0


def test_picture_present_role_filter(channel):
    product = _product(channel)
    ProductPicture.objects.create(
        product=product, picture=_make_picture(), picture_role=PictureRoleEnum.GENERAL, position=0
    )
    GapDefinitionFactory(key="picmain", check_key=GapCheck.PICTURE_PRESENT, params={"role": "main"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 1  # has GENERAL but no MAIN


# --- picture_alt_present (language-scoped, all pictures) ----------------------


def _add_picture(product, *, role=PictureRoleEnum.GENERAL, alt=None, color="red", position=0):
    return ProductPicture.objects.create(
        product=product, picture=_make_picture(color), picture_role=role, position=position, alt_text_t9n=alt or {}
    )


def test_picture_alt_missing_language_creates_finding(channel, lang_pl):
    channel.languages.add(lang_pl)  # serves en + pl
    product = _product(channel)
    _add_picture(product, alt={"en": "Red chair"})  # pl missing
    GapDefinitionFactory(key="alt", check_key=GapCheck.PICTURE_ALT_PRESENT, severity=GapSeverity.WARNING, params={})

    svc.detect_for_product(product)

    finding = _findings(product).get()  # one finding for pl only
    assert finding.language == "pl"
    assert finding.severity == GapSeverity.WARNING


def test_picture_alt_complete_no_finding(channel):
    product = _product(channel)
    _add_picture(product, alt={"en": "Red chair"})

    GapDefinitionFactory(key="alt", check_key=GapCheck.PICTURE_ALT_PRESENT, params={})
    svc.detect_for_product(product)

    assert _findings(product).count() == 0


def test_picture_alt_no_pictures_not_applicable(channel):
    product = _product(channel)
    GapDefinitionFactory(key="alt", check_key=GapCheck.PICTURE_ALT_PRESENT, params={})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0  # picture_present's gap, never double-flag


def test_picture_alt_one_of_two_pictures_missing_fails(channel):
    product = _product(channel)
    _add_picture(product, role=PictureRoleEnum.MAIN, alt={"en": "Red chair"})
    _add_picture(product, alt={"en": "  "}, color="blue", position=1)  # whitespace = empty
    GapDefinitionFactory(key="alt", check_key=GapCheck.PICTURE_ALT_PRESENT, params={})

    svc.detect_for_product(product)

    assert _findings(product).get().language == "en"


def test_picture_alt_definition_languages_narrows_check(channel, lang_pl):
    channel.languages.add(lang_pl)  # serves en + pl
    product = _product(channel)
    _add_picture(product, alt={})  # both languages missing
    GapDefinitionFactory(key="alt-en", check_key=GapCheck.PICTURE_ALT_PRESENT, params={}, languages=["en"])

    svc.detect_for_product(product)

    finding = _findings(product).get()  # pl excluded by definition.languages
    assert finding.language == "en"


# --- picture_min_count (thin gallery, language-neutral) ----------------------


def test_picture_min_count_thin_gallery_fails(channel):
    product = _product(channel)
    _add_picture(product, color="red")  # 1 picture, need 2
    GapDefinitionFactory(
        key="gallery", check_key=GapCheck.PICTURE_MIN_COUNT, severity=GapSeverity.WARNING, params={"min_count": 2}
    )

    svc.detect_for_product(product)

    finding = _findings(product).get()
    assert finding.language is None  # language-neutral, one finding
    assert finding.severity == GapSeverity.WARNING


def test_picture_min_count_enough_no_finding(channel):
    product = _product(channel)
    _add_picture(product, color="red", position=0)
    _add_picture(product, color="blue", position=1)  # 2 pictures, min_count=2
    GapDefinitionFactory(key="gallery", check_key=GapCheck.PICTURE_MIN_COUNT, params={"min_count": 2})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0


def test_picture_min_count_zero_not_applicable(channel):
    product = _product(channel)  # no pictures
    GapDefinitionFactory(key="gallery", check_key=GapCheck.PICTURE_MIN_COUNT, params={"min_count": 2})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0  # 0 = picture_present's gap, never double-flag


def test_picture_min_count_role_filter(channel):
    product = _product(channel)
    _add_picture(product, role=PictureRoleEnum.MAIN, color="red", position=0)
    _add_picture(product, role=PictureRoleEnum.GENERAL, color="blue", position=1)
    # need >=2 MAIN pictures; only 1 MAIN present → thin
    GapDefinitionFactory(
        key="gallery-main", check_key=GapCheck.PICTURE_MIN_COUNT, params={"min_count": 2, "role": "main"}
    )

    svc.detect_for_product(product)

    assert _findings(product).count() == 1


# --- category_present (structural, language-neutral) -------------------------


def test_category_present_none_fails(channel):
    product = _product(channel)  # no category assigned
    GapDefinitionFactory(key="cat", check_key=GapCheck.CATEGORY_PRESENT, severity=GapSeverity.CRITICAL, params={})

    svc.detect_for_product(product)

    finding = _findings(product).get()
    assert finding.language is None  # language-neutral, one finding
    assert finding.severity == GapSeverity.CRITICAL


def test_category_present_assigned_no_finding(channel):
    product = _product(channel)
    ProductInCategoryFactory(product=product, category=ProductCategoryFactory(shop=product.shop))
    GapDefinitionFactory(key="cat", check_key=GapCheck.CATEGORY_PRESENT, params={})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0


# --- map_attribute_to_sku (external-ref → sku index) -------------------------


def test_map_attribute_to_sku_builds_index(channel):
    from django_pim.services import product_service

    feat = FeatureFactory(idx="ext_ref", feature_type=FeatureTypeEnum.VARCHAR255, scope=FeatureScopeEnum.BUSINESS_UNIT)
    p1, p2, p3 = _product(channel), _product(channel), _product(channel)
    ProductAttribute.objects.create(product=p1, feature=feat, value_txt="111")
    ProductAttribute.objects.create(product=p2, feature=feat, value_txt="222")
    ProductAttribute.objects.create(product=p3, feature=feat, value_txt="")  # empty → excluded

    index = product_service.map_attribute_to_sku(channel.idx, "ext_ref")

    assert index == {"111": p1.real_product.sku, "222": p2.real_product.sku}


def test_picture_alt_suppressed_on_default_featureset(channel):
    # Cascade sequencing: on the placeholder set only the structural gap may surface —
    # picture_alt_present must stay quiet like every other non-structural check.
    product = _product(channel, feature_set=FeatureSetFactory(is_default=True))
    _add_picture(product, alt={})  # missing alt — would create a finding normally
    GapDefinitionFactory(key="alt", check_key=GapCheck.PICTURE_ALT_PRESENT, params={})

    svc.detect_for_product(product, skip_default=True)

    assert _findings(product).count() == 0


def test_picture_alt_inherited_points_to_default(inherited_setup):
    _default, secondary = inherited_setup
    product = ProductFactory(
        shop=secondary, feature_set=FeatureSetFactory(), real_product=RealProductFactory(), inherit_images=True
    )
    _add_picture(product, alt={})  # materialised media without alts
    GapDefinitionFactory(key="alt", check_key=GapCheck.PICTURE_ALT_PRESENT, params={})

    svc.detect_for_product(product)

    finding = _findings(product).get()
    assert finding.inherited is True
    assert finding.source_channel == "def"


# --- FeatureSet applicability ------------------------------------------------


def test_non_member_feature_is_not_applicable(channel):
    product = _product(channel)
    FeatureFactory(idx="material", feature_type=FeatureTypeEnum.VARCHAR255, scope=FeatureScopeEnum.BUSINESS_UNIT)
    GapDefinitionFactory(key="mat", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "material"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0  # "nie dotyczy"


def test_member_feature_is_evaluated(channel):
    fs = FeatureSetFactory()
    material = FeatureFactory(
        idx="material", feature_type=FeatureTypeEnum.VARCHAR255, scope=FeatureScopeEnum.BUSINESS_UNIT
    )
    FeatureInFeatureSetFactory(feature_set=fs, feature=material)
    product = _product(channel, feature_set=fs)
    GapDefinitionFactory(key="mat", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "material"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 1


# --- per-type emptiness -------------------------------------------------------


def test_bool_false_is_a_value_not_empty(channel):
    fs = FeatureSetFactory()
    flag = FeatureFactory(idx="flag", feature_type=FeatureTypeEnum.BOOL, scope=FeatureScopeEnum.BUSINESS_UNIT)
    FeatureInFeatureSetFactory(feature_set=fs, feature=flag)
    product = _product(channel, feature_set=fs)
    ProductAttribute.objects.create(product=product, feature=flag, value_bool=False)
    GapDefinitionFactory(key="b", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "flag"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0


def test_bool_missing_row_is_gap(channel):
    # ProductAttribute.save() forbids value_bool=None, so an "empty" bool = no row at all.
    fs = FeatureSetFactory()
    flag = FeatureFactory(idx="flag", feature_type=FeatureTypeEnum.BOOL, scope=FeatureScopeEnum.BUSINESS_UNIT)
    FeatureInFeatureSetFactory(feature_set=fs, feature=flag)
    product = _product(channel, feature_set=fs)
    GapDefinitionFactory(key="b", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "flag"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 1


def test_t9n_filled_in_other_language_still_gaps_missing_language(channel, lang_pl, description_feature):
    # Regression: get_value() would fall back across languages and mask the missing 'en'.
    channel.languages.add(lang_pl)  # serves en + pl
    product = _product(channel)
    ProductAttribute.objects.create(
        product=product, feature=description_feature, value_txt_t9n={"pl": "Opis po polsku"}
    )
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})

    svc.detect_for_product(product)

    langs = set(_findings(product).values_list("language", flat=True))
    assert langs == {"en"}  # pl is filled, en is genuinely missing


def test_select_with_missing_label_translation_is_not_a_gap(channel):
    # Regression: emptiness must key off attribute presence, not the localized label.
    from tests.factories import AttributeFactory

    fs = FeatureSetFactory()
    sel = FeatureFactory(idx="colour", feature_type=FeatureTypeEnum.SELECT, scope=FeatureScopeEnum.BUSINESS_UNIT)
    FeatureInFeatureSetFactory(feature_set=fs, feature=sel)
    attr = AttributeFactory(feature=sel, idx="red", name_t9n={"de": "Rot"})  # no 'en' label
    product = _product(channel, feature_set=fs)
    ProductAttribute.objects.create(product=product, feature=sel, attribute=attr)
    GapDefinitionFactory(key="c", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "colour"})

    svc.detect_for_product(product)

    assert _findings(product).count() == 0  # the select IS set, regardless of en label


# --- channel languages --------------------------------------------------------


def test_definition_all_languages_resolves_to_channel_languages(channel, lang_pl, description_feature):
    channel.languages.add(lang_pl)  # channel now serves en + pl
    product = _product(channel)
    GapDefinitionFactory(
        key="all", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"}
    )  # languages=null

    svc.detect_for_product(product)

    langs = set(_findings(product).values_list("language", flat=True))
    assert langs == {"en", "pl"}


def test_definition_language_outside_channel_is_ignored(channel, description_feature):
    product = _product(channel)  # serves only en
    GapDefinitionFactory(
        key="de", check_key=GapCheck.FEATURE_PRESENT, languages=["de"], params={"feature_idx": "description"}
    )

    svc.detect_for_product(product)

    assert _findings(product).count() == 0


# --- inherited ----------------------------------------------------------------


@pytest.fixture
def inherited_setup(db, lang_en, currency, description_feature):
    default_ch = ChannelFactory(idx="def", default_language=lang_en, default_currency=currency)
    default_ch.is_default = True
    default_ch.inheritance_enabled = True
    default_ch.save()
    secondary = ChannelFactory(idx="sec", default_language=lang_en, default_currency=currency)
    secondary.inheritance_enabled = True
    secondary.save()
    return default_ch, secondary


def test_inherited_finding_points_to_default(inherited_setup):
    _default, secondary = inherited_setup
    product = ProductFactory(
        shop=secondary, feature_set=FeatureSetFactory(), real_product=RealProductFactory(), inherit_descriptions=True
    )
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})

    svc.detect_for_product(product)

    finding = _findings(product).get()
    assert finding.inherited is True
    assert finding.source_channel == "def"


def test_overridden_language_is_not_inherited(inherited_setup, description_feature):
    _default, secondary = inherited_setup
    product = ProductFactory(
        shop=secondary, feature_set=FeatureSetFactory(), real_product=RealProductFactory(), inherit_descriptions=True
    )
    ProductAttribute.objects.create(
        product=product, feature=description_feature, value_txt_t9n={}, overridden_langs=["en"]
    )
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})

    svc.detect_for_product(product)

    finding = _findings(product).get()  # still a gap (empty), but locally owned
    assert finding.inherited is False


# --- ProductCustom ------------------------------------------------------------


def test_custom_skips_attribute_checks_runs_pictures(channel, description_feature):
    custom = models.ProductCustom.objects.create(
        shop=channel, feature_set=FeatureSetFactory(), real_product=RealProductFactory()
    )
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})
    GapDefinitionFactory(key="pic", check_key=GapCheck.PICTURE_PRESENT, severity=GapSeverity.WARNING, params={})

    svc.detect_for_product(custom)

    finding = _findings(custom).get()  # only the picture check ran
    assert finding.definition.check_key == GapCheck.PICTURE_PRESENT
    base = models.Product.objects.get(pk=custom.pk)
    assert base.gap_evaluated_at is None  # "nieoceniony" — distinguishable from OK
    assert base.gap_count == 1


# --- idempotency + silent rollup + worst severity ----------------------------


def test_detect_is_idempotent(channel, description_feature):
    product = _product(channel)
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})

    svc.detect_for_product(product)
    svc.detect_for_product(product)

    assert _findings(product).count() == 1


def test_rollup_written_silently_via_update(channel, description_feature):
    product = _product(channel)
    GapDefinitionFactory(key="d", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})
    product.refresh_from_db()
    before = product.db_modified

    svc.detect_for_product(product)

    product.refresh_from_db()
    assert product.db_modified == before  # auto_now untouched → .update(), not .save()
    assert product.gap_count == 1


def test_worst_severity_is_critical_when_mixed(channel, description_feature):
    product = _product(channel)
    GapDefinitionFactory(
        key="c",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )
    GapDefinitionFactory(key="w", check_key=GapCheck.PICTURE_PRESENT, severity=GapSeverity.WARNING, params={})

    svc.detect_for_product(product)

    product.refresh_from_db()
    assert product.gap_count == 2
    assert product.gap_worst_severity == GapSeverity.CRITICAL


# --- params allowlist ---------------------------------------------------------


def test_validate_params_rejects_unknown_key():
    with pytest.raises(ValueError):
        registry.validate_params(GapCheck.FEATURE_PRESENT, {"feature_idx": "x", "bogus": 1})


def test_validate_params_requires_feature_idx():
    with pytest.raises(ValueError):
        registry.validate_params(GapCheck.FEATURE_PRESENT, {})


def test_invalid_definition_is_skipped_not_fatal(channel, description_feature):
    product = _product(channel)
    GapDefinitionFactory(key="bad", check_key=GapCheck.FEATURE_PRESENT, params={})  # missing feature_idx
    GapDefinitionFactory(key="good", check_key=GapCheck.FEATURE_PRESENT, params={"feature_idx": "description"})

    svc.detect_for_product(product)  # must not raise

    assert _findings(product).count() == 1


# --- rollup repair without re-detection (etap-03) ----------------------------


def test_recompute_rollup_from_current_findings_is_silent(channel, description_feature):
    """recompute_rollup_for_products reflects CURRENT findings, leaves evaluated_at, fires no signals."""
    from django_pim.services import gap_recompute_service

    product = _product(channel)
    definition = GapDefinitionFactory(
        key="r", check_key=GapCheck.FEATURE_PRESENT, severity=GapSeverity.WARNING, params={"feature_idx": "description"}
    )
    svc.detect_for_product(product)  # 1 WARNING finding, rollup populated
    product.refresh_from_db()
    evaluated_before = product.gap_evaluated_at
    db_modified_before = product.db_modified

    # Drop the finding directly, then repair the rollup from current state.
    models.GapFinding.objects.filter(product=product, definition=definition).delete()
    gap_recompute_service.recompute_rollup_for_products([product.pk])

    product.refresh_from_db()
    assert product.gap_count == 0
    assert product.gap_worst_severity is None
    assert product.gap_evaluated_at == evaluated_before  # not a re-evaluation
    assert product.db_modified == db_modified_before  # silent .update() — no post_save


def test_recompute_rollup_picks_worst_severity(channel, description_feature):
    from django_pim.services import gap_recompute_service

    product = _product(channel)
    crit = GapDefinitionFactory(key="c", severity=GapSeverity.CRITICAL, params={"feature_idx": "description"})
    warn = GapDefinitionFactory(key="w", severity=GapSeverity.WARNING, params={"feature_idx": "description"})
    models.GapFinding.objects.create(
        product=product, definition=crit, channel_idx=channel.idx, severity=GapSeverity.CRITICAL, language="en"
    )
    models.GapFinding.objects.create(
        product=product, definition=warn, channel_idx=channel.idx, severity=GapSeverity.WARNING, language="en"
    )

    gap_recompute_service.recompute_rollup_for_products([product.pk])

    product.refresh_from_db()
    assert product.gap_count == 2
    assert product.gap_worst_severity == GapSeverity.CRITICAL


# --- propagation hook (bulk writes don't signal → explicit enqueue) ----------


def test_propagation_hook_enqueues_children_when_enabled(channel):
    from django.core.cache import cache

    from django_pim.models.pim_settings import PimSettings
    from django_pim.services import inheritance_service

    s = PimSettings.load()
    s.gaps_enabled = True
    s.save()
    cache.delete("pim:gaps_enabled")

    with patch("django_pim.signals.dispatch.enqueue_gap_recompute") as mock_enqueue:
        inheritance_service._enqueue_gap_recompute_for_children([101, 202])

    assert mock_enqueue.call_count == 2
    mock_enqueue.assert_any_call(101)
    mock_enqueue.assert_any_call(202)


def test_propagation_hook_noop_when_disabled():
    from django.core.cache import cache

    from django_pim.models.pim_settings import PimSettings
    from django_pim.services import inheritance_service

    s = PimSettings.load()
    s.gaps_enabled = False
    s.save()
    cache.delete("pim:gaps_enabled")

    with patch("django_pim.signals.dispatch.enqueue_gap_recompute") as mock_enqueue:
        inheritance_service._enqueue_gap_recompute_for_children([101])

    mock_enqueue.assert_not_called()


# --- feature_set_default + skip-default sequencing (featureset-cascade etap-01)


def _seed_cascade_rules():
    """One structural rule + one attribute rule — the muting interplay under test."""
    GapDefinitionFactory(
        key="fs-default", check_key=GapCheck.FEATURE_SET_DEFAULT, severity=GapSeverity.CRITICAL, params={}
    )
    GapDefinitionFactory(
        key="d",
        check_key=GapCheck.FEATURE_PRESENT,
        severity=GapSeverity.CRITICAL,
        params={"feature_idx": "description"},
    )


def test_default_set_with_flag_on_yields_only_structural_gap(channel, description_feature):
    product = _product(channel, feature_set=FeatureSetFactory(is_default=True))
    _seed_cascade_rules()

    svc.detect_for_product(product)

    finding = _findings(product).get()  # exactly one — attribute gap muted
    assert finding.definition.key == "fs-default"
    assert finding.language is None  # structural, language-neutral
    product.refresh_from_db()
    assert product.gap_count == 1
    assert product.gap_worst_severity == GapSeverity.CRITICAL


def test_real_set_passes_structural_check(channel, description_feature):
    product = _product(channel)  # factory set is_default=False
    _seed_cascade_rules()

    svc.detect_for_product(product)

    keys = set(_findings(product).values_list("definition__key", flat=True))
    assert keys == {"d"}  # description gap fires; structural check passes


def test_flag_off_structural_and_attribute_findings_coexist(channel, description_feature):
    settings = models.PimSettings.load()
    settings.gaps_skip_default_featureset = False
    settings.save()
    product = _product(channel, feature_set=FeatureSetFactory(is_default=True))
    _seed_cascade_rules()

    svc.detect_for_product(product)

    keys = set(_findings(product).values_list("definition__key", flat=True))
    assert keys == {"fs-default", "d"}  # flag only disables the muting


def test_skip_default_injection_overrides_settings(channel, description_feature):
    """Batch parity: the injected flag wins over PimSettings (read once per batch)."""
    product = _product(channel, feature_set=FeatureSetFactory(is_default=True))
    _seed_cascade_rules()

    svc.detect_for_product(product, skip_default=False)
    keys = set(_findings(product).values_list("definition__key", flat=True))
    assert keys == {"fs-default", "d"}

    svc.detect_for_product(product, skip_default=True)  # idempotent replace clears the muted gap
    keys = set(_findings(product).values_list("definition__key", flat=True))
    assert keys == {"fs-default"}


def test_validate_params_rejects_params_for_feature_set_default():
    with pytest.raises(ValueError):
        registry.validate_params(GapCheck.FEATURE_SET_DEFAULT, {"feature_idx": "x"})


def test_batch_recompute_reads_skip_flag_once_and_threads_it(channel, description_feature):
    """The production batch path (_recompute_qs via recompute_pks) must honor the PimSettings
    flag end-to-end — a dropped kwarg would silently disable the cascade muting at scale."""
    from django_pim.services import gap_recompute_service

    product = _product(channel, feature_set=FeatureSetFactory(is_default=True))
    _seed_cascade_rules()

    gap_recompute_service.recompute_pks([product.pk])
    keys = set(_findings(product).values_list("definition__key", flat=True))
    assert keys == {"fs-default"}  # flag default True → muted

    settings = models.PimSettings.load()
    settings.gaps_skip_default_featureset = False
    settings.save()

    gap_recompute_service.recompute_pks([product.pk])
    keys = set(_findings(product).values_list("definition__key", flat=True))
    assert keys == {"fs-default", "d"}  # flag off → coexist, batch path included


def test_custom_product_on_default_set_keeps_structural_gap(channel, description_feature):
    """ProductCustom × skip-default precedence: the structural check (reads_attributes=False)
    survives the custom skip; evaluated_at stays NULL ("nieoceniony")."""
    from django_pim.models.product import ProductClassEnum

    product = ProductFactory(
        shop=channel,
        feature_set=FeatureSetFactory(is_default=True),
        real_product=RealProductFactory(),
        product_class=ProductClassEnum.ProductCustom,
    )
    _seed_cascade_rules()

    svc.detect_for_product(product)

    keys = set(_findings(product).values_list("definition__key", flat=True))
    assert keys == {"fs-default"}
    product.refresh_from_db()
    assert product.gap_evaluated_at is None  # custom stays "nieoceniony"
