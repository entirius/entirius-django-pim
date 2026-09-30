# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""create_product: required-feature enforcement and strict create (both off by default)."""

from decimal import Decimal

import pytest

from django_pim.exceptions import RequiredFeaturesMissingError, UnresolvedAttributesError
from django_pim.models import (
    FeatureScopeEnum,
    FeatureTypeEnum,
    Product,
    ProductAttribute,
    ProductInCategory,
    RealProduct,
)
from django_pim.services import product_service

from .factories import (
    AttributeFactory,
    ChannelFactory,
    FeatureFactory,
    FeatureInFeatureSetFactory,
    FeatureSetFactory,
    ProductCategoryFactory,
)

T = FeatureTypeEnum


def _required(idx: str, feature_type: int, fs, **kwargs):
    feature = FeatureFactory(idx=idx, feature_type=feature_type, is_required=True, **kwargs)
    FeatureInFeatureSetFactory(feature_set=fs, feature=feature)
    return feature


@pytest.fixture
def channel(db):
    return ChannelFactory(idx="shop")


@pytest.fixture
def fs(db):
    return FeatureSetFactory(idx="battery")


@pytest.fixture
def voltage(fs):
    return _required("voltage", T.DECIMAL, fs)


def _create(attributes=None, *, sku="SKU-1", **kwargs):
    return product_service.create_product(
        channel_idx="shop", sku=sku, feature_set_idx="battery", attributes=attributes, **kwargs
    )


def _assert_nothing_written():
    assert RealProduct.objects.count() == 0
    assert Product.objects.count() == 0
    assert ProductAttribute.objects.count() == 0


def _has_value(pa: ProductAttribute) -> bool:
    """Independent restatement of 'non-empty stored row' (bool False / decimal 0 count)."""
    if pa.attribute_id:
        return True
    for value in (pa.value_bool, pa.value_decimal, pa.value_datetime):
        if value is not None:
            return True
    if pa.value_txt and pa.value_txt.strip():
        return True
    if pa.value_txt_t9n and any((v or "").strip() for v in pa.value_txt_t9n.values()):
        return True
    return bool(pa.value_json)


class TestErrorTypes:
    def test_required_error_is_not_a_value_error(self):
        err = RequiredFeaturesMissingError("battery", ["b", "a"])

        assert not isinstance(err, ValueError)
        assert err.feature_set_idx == "battery"
        assert err.missing_feature_idxs == ["a", "b"]

    def test_unresolved_error_is_not_a_value_error(self):
        err = UnresolvedAttributesError(unresolved_attributes=["x"], unknown_category_idxs=["c"])

        assert not isinstance(err, ValueError)
        assert (err.unresolved_attributes, err.unknown_category_idxs) == (["x"], ["c"])


@pytest.mark.django_db
class TestEnforcementSwitch:
    def test_default_keeps_3_2_behaviour(self, channel, voltage):
        assert _create().pk

    def test_kwarg_true_refuses_before_any_write(self, channel, voltage):
        with pytest.raises(RequiredFeaturesMissingError) as exc:
            _create(enforce_required=True)

        assert exc.value.feature_set_idx == "battery"
        assert exc.value.missing_feature_idxs == ["voltage"]
        _assert_nothing_written()

    def test_setting_enables(self, channel, voltage, settings):
        settings.PIM_ENFORCE_REQUIRED_ON_CREATE = True

        with pytest.raises(RequiredFeaturesMissingError):
            _create()

    def test_kwarg_false_overrides_setting(self, channel, voltage, settings):
        settings.PIM_ENFORCE_REQUIRED_ON_CREATE = True

        assert _create(enforce_required=False).pk

    def test_setting_is_read_at_call_time(self, channel, voltage, settings):
        assert _create(sku="A").pk
        settings.PIM_ENFORCE_REQUIRED_ON_CREATE = True
        with pytest.raises(RequiredFeaturesMissingError):
            _create(sku="B")

    def test_supplied_required_value_creates(self, channel, voltage):
        product = _create([{"feature_idx": "voltage", "value_decimal": "48"}], enforce_required=True)

        assert ProductAttribute.objects.filter(product=product, feature=voltage).count() == 1

    def test_missing_idxs_are_sorted(self, channel, fs):
        for idx in ("zz", "mm", "aa"):
            _required(idx, T.DECIMAL, fs)

        with pytest.raises(RequiredFeaturesMissingError) as exc:
            _create(enforce_required=True)

        assert exc.value.missing_feature_idxs == ["aa", "mm", "zz"]

    def test_duplicate_sku_is_still_a_value_error_and_comes_first(self, channel, voltage):
        _create([{"feature_idx": "voltage", "value_decimal": "1"}], enforce_required=True)

        with pytest.raises(ValueError, match="already exists") as exc:
            _create(enforce_required=True)

        assert not isinstance(exc.value, RequiredFeaturesMissingError)

    def test_unknown_channel_and_set_still_raise_does_not_exist_first(self, channel, voltage):
        from django_pim.models import Channel, FeatureSet

        with pytest.raises(Channel.DoesNotExist):
            product_service.create_product(
                channel_idx="nope", sku="X", feature_set_idx="battery", enforce_required=True
            )
        with pytest.raises(FeatureSet.DoesNotExist):
            product_service.create_product(channel_idx="shop", sku="X", feature_set_idx="nope", enforce_required=True)

    def test_set_override_false_is_not_enforced(self, channel, fs):
        feature = FeatureFactory(idx="voltage", feature_type=T.DECIMAL, is_required=True)
        FeatureInFeatureSetFactory(feature_set=fs, feature=feature, is_required=False)

        assert _create(enforce_required=True).pk

    def test_set_override_true_is_enforced(self, channel, fs):
        feature = FeatureFactory(idx="voltage", feature_type=T.DECIMAL, is_required=False)
        FeatureInFeatureSetFactory(feature_set=fs, feature=feature, is_required=True)

        with pytest.raises(RequiredFeaturesMissingError):
            _create(enforce_required=True)

    def test_system_required_feature_is_enforced(self, channel, fs):
        FeatureFactory(idx="name", feature_type=T.VARCHAR255_T9N, is_required=True, scope=FeatureScopeEnum.SYSTEM)

        with pytest.raises(RequiredFeaturesMissingError) as exc:
            _create(enforce_required=True)
        assert exc.value.missing_feature_idxs == ["name"]
        assert _create([{"feature_idx": "name", "value_txt_t9n": {"en": "Pack"}}], enforce_required=True).pk


@pytest.mark.django_db
class TestWhatCountsAsSupplied:
    """Only values that will actually be stored, and non-empty, satisfy a required feature."""

    @pytest.fixture(autouse=True)
    def _features(self, channel, fs):
        self.features = {
            "dec": _required("dec", T.DECIMAL, fs),
            "flag": _required("flag", T.BOOL, fs),
            "txt": _required("txt", T.VARCHAR255, fs),
            "t9n": _required("t9n", T.TEXT_T9N, fs),
            "js": _required("js", T.JSON, fs),
            "sel": _required("sel", T.SELECT, fs),
            "multi": _required("multi", T.MULTISELECT, fs),
        }
        other = FeatureFactory(idx="other", feature_type=T.SELECT)
        AttributeFactory(idx="red", feature=self.features["sel"])
        AttributeFactory(idx="a", feature=self.features["multi"])
        AttributeFactory(idx="b", feature=self.features["multi"])
        AttributeFactory(idx="foreign", feature=other)

    @pytest.mark.parametrize(
        "attribute",
        [
            {"feature_idx": "ghost", "value_txt": "x"},
            {"feature_idx": "txt", "value_txt": ""},
            {"feature_idx": "txt", "value_txt": "   "},
            {"feature_idx": "txt"},
            {"feature_idx": "dec", "value_txt": "12"},
            {"feature_idx": "dec", "value_decimal": None},
            {"feature_idx": "flag", "value_bool": None},
            {"feature_idx": "t9n", "value_txt_t9n": {"en": "", "pl": "  "}},
            {"feature_idx": "t9n", "value_txt_t9n": {}},
            {"feature_idx": "js", "value_json": {}},
            {"feature_idx": "js", "value_json": None},
            {"feature_idx": "sel", "attribute_idx": "missing"},
            {"feature_idx": "sel", "attribute_idx": "foreign"},
            {"feature_idx": "sel", "attribute_idx": None},
            {"feature_idx": "multi", "attribute_idxs": []},
            {"feature_idx": "multi", "attribute_idxs": ["missing", "foreign"]},
        ],
        ids=lambda a: f"{a['feature_idx']}-{sorted(set(a) - {'feature_idx'})}-{list(a.values())[-1]!r}",
    )
    def test_does_not_count(self, attribute, fs):
        missing = product_service.find_missing_required(fs, [attribute])

        assert missing == sorted(self.features)

    @pytest.mark.parametrize(
        "attribute",
        [
            {"feature_idx": "dec", "value_decimal": "0"},
            {"feature_idx": "flag", "value_bool": False},
            {"feature_idx": "txt", "value_txt": "x"},
            {"feature_idx": "t9n", "value_txt_t9n": {"en": "", "pl": "ok"}},
            {"feature_idx": "js", "value_json": {"k": 1}},
            {"feature_idx": "sel", "attribute_idx": "red"},
            {"feature_idx": "multi", "attribute_idxs": ["a", "missing"]},
        ],
        ids=lambda a: a["feature_idx"],
    )
    def test_counts(self, attribute, fs):
        missing = product_service.find_missing_required(fs, [attribute])

        assert missing == sorted(set(self.features) - {attribute["feature_idx"]})

    def test_find_missing_required_is_sorted_and_complete(self, fs):
        assert product_service.find_missing_required(fs, None) == sorted(self.features)
        assert product_service.find_missing_required(fs, []) == sorted(self.features)

    def test_plan_equals_stored_rows(self, fs):
        """What the check counts is exactly what the write step stores (non-empty rows)."""
        attributes = [
            {"feature_idx": "dec", "value_decimal": "0"},
            {"feature_idx": "flag", "value_bool": False},
            {"feature_idx": "txt", "value_txt": ""},
            {"feature_idx": "t9n", "value_txt_t9n": {"en": "x"}},
            {"feature_idx": "js", "value_json": {}},
            {"feature_idx": "sel", "attribute_idx": "foreign"},
            {"feature_idx": "multi", "attribute_idxs": ["a", "b", "missing"]},
            {"feature_idx": "ghost", "value_txt": "x"},
        ]
        counted = set(self.features) - set(product_service.find_missing_required(fs, attributes))

        product = _create(attributes)
        stored = {
            pa.feature.idx
            for pa in ProductAttribute.objects.filter(product=product).select_related("feature", "attribute")
            if _has_value(pa)
        }

        assert counted == stored == {"dec", "flag", "t9n", "multi"}


@pytest.mark.django_db
class TestStrictCreate:
    @pytest.fixture(autouse=True)
    def _features(self, channel, fs):
        self.sel = FeatureFactory(idx="sel", feature_type=T.SELECT)
        FeatureInFeatureSetFactory(feature_set=fs, feature=self.sel)
        self.other = FeatureFactory(idx="other", feature_type=T.SELECT)
        AttributeFactory(idx="red", feature=self.sel)
        AttributeFactory(idx="foreign", feature=self.other)
        self.category = ProductCategoryFactory(idx="cat", shop=channel)

    def test_default_silently_drops(self):
        product = _create(
            [{"feature_idx": "ghost", "value_txt": "x"}, {"feature_idx": "sel", "attribute_idx": "nope"}],
            category_idxs=["nope"],
        )

        assert ProductAttribute.objects.filter(product=product).count() == 0
        assert ProductInCategory.objects.filter(product=product).count() == 0

    @pytest.mark.parametrize(
        ("attributes", "categories", "unresolved_attrs", "unknown_cats"),
        [
            ([{"feature_idx": "ghost", "value_txt": "x"}], None, ["ghost"], []),
            ([{"feature_idx": "sel", "attribute_idx": "nope"}], None, ["sel"], []),
            ([{"feature_idx": "sel", "attribute_idx": "foreign"}], None, ["sel"], []),
            (None, ["nope", "cat"], [], ["nope"]),
            ([{"feature_idx": "ghost", "value_txt": "x"}], ["nope"], ["ghost"], ["nope"]),
        ],
    )
    def test_strict_refuses_before_any_write(self, attributes, categories, unresolved_attrs, unknown_cats):
        with pytest.raises(UnresolvedAttributesError) as exc:
            _create(attributes, category_idxs=categories, strict=True)

        assert exc.value.unresolved_attributes == unresolved_attrs
        assert exc.value.unknown_category_idxs == unknown_cats
        _assert_nothing_written()

    def test_multiselect_bad_option_is_reported(self, fs):
        multi = FeatureFactory(idx="multi", feature_type=T.MULTISELECT)
        FeatureInFeatureSetFactory(feature_set=fs, feature=multi)
        AttributeFactory(idx="a", feature=multi)

        with pytest.raises(UnresolvedAttributesError) as exc:
            _create([{"feature_idx": "multi", "attribute_idxs": ["a", "nope"]}], strict=True)

        assert exc.value.unresolved_attributes == ["multi"]

    def test_strict_ok_when_everything_resolves(self):
        product = _create(
            [{"feature_idx": "sel", "attribute_idx": "red"}, {"feature_idx": "sel"}], category_idxs=["cat"], strict=True
        )

        assert ProductAttribute.objects.filter(product=product).count() == 1
        assert ProductInCategory.objects.filter(product=product).count() == 1

    def test_clearing_a_select_with_null_is_not_a_drop(self):
        assert _create([{"feature_idx": "sel", "attribute_idx": None}], strict=True).pk

    def test_setting_enables_and_kwarg_overrides(self, settings):
        settings.PIM_STRICT_CREATE = True
        with pytest.raises(UnresolvedAttributesError):
            _create([{"feature_idx": "ghost", "value_txt": "x"}], sku="A")

        assert _create([{"feature_idx": "ghost", "value_txt": "x"}], sku="B", strict=False).pk

    def test_strict_runs_before_required_check(self, fs):
        _required("need", T.DECIMAL, fs)

        with pytest.raises(UnresolvedAttributesError):
            _create([{"feature_idx": "ghost", "value_txt": "x"}], strict=True, enforce_required=True)

    def test_duplicate_sku_still_first(self):
        _create()

        with pytest.raises(ValueError, match="already exists"):
            _create([{"feature_idx": "ghost", "value_txt": "x"}], strict=True)


@pytest.mark.django_db
class TestUnitFeaturesAreStored:
    """LENGTH / MASS / TEMPERATURE travel in value_decimal; create must store it (and count it)."""

    @pytest.mark.parametrize("feature_type", [T.LENGTH, T.MASS, T.TEMPERATURE])
    def test_value_is_stored_and_satisfies_required(self, channel, fs, feature_type):
        feature = _required("unit", feature_type, fs)

        product = _create([{"feature_idx": "unit", "value_decimal": "12.5"}], enforce_required=True)

        assert ProductAttribute.objects.get(product=product, feature=feature).value_decimal == Decimal("12.5")
