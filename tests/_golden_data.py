# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generator + builder for the golden-gaps fixture (etap-07).

This module is the *regenerable source* for ``tests/fixtures/gaps_golden.yaml`` (and its mirror in
entirius-test-package). It is NOT a test (no ``test_`` prefix → pytest never collects it).

The fixture is a small, deterministic catalogue that exercises the gap-detection golden rules:
inheritance, ProductCustom "nieoceniony", FeatureSet applicability, and per-type emptiness for
MULTISELECT + DECIMAL — the cases per-stage tests do NOT already cover (the rest live in
``test_services.py`` etc.). Every object carries a ``golden-`` idx so it is self-contained and never
collides with seeded system features.

Regenerate (against the reusable test DB):

    DJANGO_SETTINGS_MODULE=tests.settings \\
        python -c "from tests._golden_data import emit_fixture; emit_fixture()"

It builds the objects in a transaction, serialises them to YAML, then rolls back — the test DB is
left untouched. Copy the emitted file to entirius-test-package/fixtures/django_pim_gaps_golden.cfg.yaml.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django_pim.models import FeatureScopeEnum, FeatureTypeEnum, ProductAttribute
from django_pim.models.gap_definition import GapCheck, GapSeverity
from django_pim.models.product import ProductClassEnum

# Channels
CH_DEFAULT = "golden-default"
CH_SEC = "golden-sec"
# Features
F_DESC = "golden-desc"  # TEXT_T9N, SYSTEM → always applicable
F_MATERIAL = "golden-material"  # VARCHAR255, BU
F_TAGS = "golden-tags"  # MULTISELECT, BU
F_WEIGHT = "golden-weight"  # DECIMAL, BU
# Feature sets
FS_EMPTY = "golden-fs-empty"
FS_FULL = "golden-fs-full"
FS_DEFAULT = "golden-fs-default"  # is_default=True — the importer placeholder set
# Gap definition keys
G_DESC = "golden-desc-present"
G_DESC_MIN = "golden-desc-min"
G_MATERIAL = "golden-material-present"
G_TAGS = "golden-tags-present"
G_WEIGHT = "golden-weight-present"
G_PICTURE = "golden-main-picture"
G_FS_DEFAULT = "golden-featureset-default"  # classification gap (featureset-cascade etap-01)
# Products (real_product sku == product slug, one Product per channel)
P_MISSING_DESC = "p-missing-desc"
P_DESC_OK = "p-desc-ok"
P_SHORT_DESC = "p-short-desc"
P_CUSTOM = "p-custom"
P_MULTI_EMPTY = "p-multi-empty"
P_MULTI_FILLED = "p-multi-filled"
P_DECIMAL_ZERO = "p-decimal-zero"
P_DECIMAL_MISSING = "p-decimal-missing"
P_INHERIT = "p-inherit"  # shared sku → one Product on default (source), one on sec (inheriting child)
P_ON_DEFAULT = "p-on-default"  # parked on the placeholder set → only the structural gap (skip-default)

_LONG_DESC = "x" * 130  # ≥ 120 chars → passes both feature_present and feature_min_length(120)


# --- shared helpers for the golden test suites (test_correctness_golden, test_cascade_golden) ---


def _product(sku: str, channel_idx: str):
    from django_pim import models

    return models.Product.objects.get(real_product__sku=sku, shop__idx=channel_idx)


def _detect(sku: str, channel_idx: str = CH_SEC):
    """Fetch the product and run gap detection on it (synchronous, deterministic)."""
    from django_pim.services import gap_detection_service as svc

    product = _product(sku, channel_idx)
    svc.detect_for_product(product)
    return product


def _keys(product) -> set[str]:
    """Definition keys of the product's current findings."""
    from django_pim import models

    return set(models.GapFinding.objects.filter(product=product).values_list("definition__key", flat=True))


def build_golden_objects() -> list:
    """Create the deterministic golden catalogue and return all rows in load order."""
    from tests.factories import (
        AttributeFactory,
        ChannelFactory,
        CurrencyFactory,
        FeatureFactory,
        FeatureInFeatureSetFactory,
        FeatureSetFactory,
        GapDefinitionFactory,
        LanguageFactory,
        ProductFactory,
        RealProductFactory,
    )

    objs: list = []

    # --- locale ---------------------------------------------------------------
    en = LanguageFactory(iso2="EN", iso3="ENG")
    pl = LanguageFactory(iso2="PL", iso3="POL")
    eur = CurrencyFactory(iso3="EUR")
    objs += [en, pl, eur]

    # --- channels (default serves en+pl, secondary serves en only) -----------
    default = ChannelFactory(
        idx=CH_DEFAULT,
        name="Golden Default",
        default_language=en,
        default_currency=eur,
        is_default=True,
        inheritance_enabled=True,
    )
    default.languages.add(pl)
    sec = ChannelFactory(
        idx=CH_SEC,
        name="Golden Secondary",
        default_language=en,
        default_currency=eur,
        is_default=False,
        inheritance_enabled=True,
    )
    objs += [default, sec]

    # --- features -------------------------------------------------------------
    # Cast enums to plain int — the YAML serializer cannot represent IntEnum instances.
    f_desc = FeatureFactory(
        idx=F_DESC,
        feature_type=int(FeatureTypeEnum.TEXT_T9N),
        scope=int(FeatureScopeEnum.SYSTEM),
        display_order=10,
        name_t9n={"en": "Description"},
    )
    f_material = FeatureFactory(
        idx=F_MATERIAL,
        feature_type=int(FeatureTypeEnum.VARCHAR255),
        scope=int(FeatureScopeEnum.BUSINESS_UNIT),
        display_order=20,
        name_t9n={"en": "Material"},
    )
    f_tags = FeatureFactory(
        idx=F_TAGS,
        feature_type=int(FeatureTypeEnum.MULTISELECT),
        scope=int(FeatureScopeEnum.BUSINESS_UNIT),
        display_order=30,
        name_t9n={"en": "Tags"},
    )
    f_weight = FeatureFactory(
        idx=F_WEIGHT,
        feature_type=int(FeatureTypeEnum.DECIMAL),
        scope=int(FeatureScopeEnum.BUSINESS_UNIT),
        display_order=40,
        name_t9n={"en": "Weight"},
    )
    objs += [f_desc, f_material, f_tags, f_weight]

    # --- feature sets (empty = BU features not applicable; full = applicable) -
    fs_empty = FeatureSetFactory(idx=FS_EMPTY, name="Golden FS Empty")
    fs_full = FeatureSetFactory(idx=FS_FULL, name="Golden FS Full")
    fs_default = FeatureSetFactory(idx=FS_DEFAULT, name="Golden FS Default", is_default=True)
    objs += [fs_empty, fs_full, fs_default]
    objs += [
        FeatureInFeatureSetFactory(feature_set=fs_full, feature=f_material, position=20),
        FeatureInFeatureSetFactory(feature_set=fs_full, feature=f_tags, position=30),
        FeatureInFeatureSetFactory(feature_set=fs_full, feature=f_weight, position=40),
    ]

    # --- one multiselect attribute value (for the "filled" case) -------------
    tag_a = AttributeFactory(feature=f_tags, idx="golden-tag-a", name_t9n={"en": "Tag A"})
    objs.append(tag_a)

    # --- gap definitions (languages=[en] → deterministic single finding) -----
    # check_key/severity cast to str — keep the serialized YAML free of enum instances.
    _crit = str(GapSeverity.CRITICAL)
    _warn = str(GapSeverity.WARNING)
    _present = str(GapCheck.FEATURE_PRESENT)
    objs += [
        GapDefinitionFactory(
            key=G_DESC,
            check_key=_present,
            severity=_crit,
            params={"feature_idx": F_DESC},
            languages=["en"],
            label_t9n={"en": "Missing description"},
            display_order=10,
        ),
        GapDefinitionFactory(
            key=G_DESC_MIN,
            check_key=str(GapCheck.FEATURE_MIN_LENGTH),
            severity=_warn,
            params={"feature_idx": F_DESC, "min_length": 120},
            languages=["en"],
            label_t9n={"en": "Description too short"},
            display_order=20,
        ),
        GapDefinitionFactory(
            key=G_MATERIAL,
            check_key=_present,
            severity=_crit,
            params={"feature_idx": F_MATERIAL},
            languages=["en"],
            label_t9n={"en": "Missing material"},
            display_order=30,
        ),
        GapDefinitionFactory(
            key=G_TAGS,
            check_key=_present,
            severity=_warn,
            params={"feature_idx": F_TAGS},
            languages=["en"],
            label_t9n={"en": "Missing tags"},
            display_order=40,
        ),
        GapDefinitionFactory(
            key=G_WEIGHT,
            check_key=_present,
            severity=_warn,
            params={"feature_idx": F_WEIGHT},
            languages=["en"],
            label_t9n={"en": "Missing weight"},
            display_order=50,
        ),
        GapDefinitionFactory(
            key=G_PICTURE,
            check_key=str(GapCheck.PICTURE_PRESENT),
            severity=_crit,
            params={"role": "main"},
            languages=None,  # picture check is language-neutral (unlike the en-scoped feature rules)
            label_t9n={"en": "Missing main picture"},
            display_order=60,
        ),
        GapDefinitionFactory(
            key=G_FS_DEFAULT,
            check_key=str(GapCheck.FEATURE_SET_DEFAULT),
            severity=_crit,
            params={},
            languages=None,  # structural, language-neutral
            label_t9n={"en": "Product on default feature set"},
            display_order=5,  # head of the cascade — listed before everything else
        ),
    ]

    # --- products -------------------------------------------------------------
    def _make_product(
        slug,
        *,
        shop=sec,
        feature_set=fs_empty,
        product_class=ProductClassEnum.ProductSimple,
        inherit_attributes=False,
        real_product=None,
    ):
        rp = real_product or RealProductFactory(sku=slug)
        if real_product is None:
            objs.append(rp)
        p = ProductFactory(
            shop=shop,
            feature_set=feature_set,
            real_product=rp,
            product_class=int(product_class),
            inherit_attributes=inherit_attributes,
            is_enabled=True,
        )
        objs.append(p)
        return p

    def _attr(product, feature, **values):
        pa = ProductAttribute.objects.create(product=product, feature=feature, **values)
        objs.append(pa)
        return pa

    # FeatureSet applicability + description present/short
    _make_product(P_MISSING_DESC)  # desc-present fires; material/tags/weight NOT applicable (empty fs)
    p_ok = _make_product(P_DESC_OK)
    _attr(p_ok, f_desc, value_txt_t9n={"en": _LONG_DESC})  # present + long → neither desc gap
    p_short = _make_product(P_SHORT_DESC)
    _attr(p_short, f_desc, value_txt_t9n={"en": "abc"})  # present but short → only desc-min

    # ProductCustom → attribute checks skipped, picture check still runs, evaluated_at stays NULL
    _make_product(P_CUSTOM, product_class=ProductClassEnum.ProductCustom)

    # Per-type emptiness: MULTISELECT
    _make_product(P_MULTI_EMPTY, feature_set=fs_full)  # no tags row → tags gap
    p_multi_filled = _make_product(P_MULTI_FILLED, feature_set=fs_full)
    _attr(p_multi_filled, f_tags, attribute=tag_a)  # one selection → no tags gap

    # Per-type emptiness: DECIMAL (0 is a value, not empty)
    p_dec_zero = _make_product(P_DECIMAL_ZERO, feature_set=fs_full)
    _attr(p_dec_zero, f_weight, value_decimal=Decimal("0"))  # 0 = set → no weight gap
    _make_product(P_DECIMAL_MISSING, feature_set=fs_full)  # no weight row → weight gap

    # Inheritance: ONE real_product, source on default (material filled), inheriting child on sec.
    # Uses a BU feature in the shared (full) FeatureSet so real propagation materialises it onto the
    # child — letting the E2E prove the inherited finding clears after a fix on the default channel.
    rp_inherit = RealProductFactory(sku=P_INHERIT)
    objs.append(rp_inherit)
    src = _make_product(P_INHERIT, shop=default, feature_set=fs_full, real_product=rp_inherit)
    _attr(src, f_material, value_txt="Solid oak")
    _make_product(P_INHERIT, shop=sec, feature_set=fs_full, real_product=rp_inherit, inherit_attributes=True)

    # Skip-default sequencing: parked on the placeholder set, missing desc AND picture — with the
    # flag on, only the structural classification gap may surface (featureset-cascade etap-01).
    _make_product(P_ON_DEFAULT, shop=sec, feature_set=fs_default)

    return objs


def emit_fixture(path: str | None = None) -> str:
    """Build the catalogue in a rolled-back transaction and write the YAML fixture."""
    from django.core import serializers
    from django.db import transaction

    @transaction.atomic
    def _dump() -> str:
        objs = build_golden_objects()
        # Reload so scalar fields hold plain ints/strings, not in-memory enum instances
        # (the YAML serializer cannot represent IntEnum / TextChoices objects).
        for obj in objs:
            obj.refresh_from_db()
        data = serializers.serialize("yaml", objs, indent=2)
        transaction.set_rollback(True)  # leave the DB exactly as we found it
        return data

    data = _dump()
    target = Path(path) if path else Path(__file__).parent / "fixtures" / "gaps_golden.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data)
    print(f"wrote {target} ({len(data)} bytes)")
    return str(target)
