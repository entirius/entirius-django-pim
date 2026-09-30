# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Required per feature set: nullable override on the membership, effective flag, required set."""

import itertools

import pytest

from django_pim.models import FeatureInFeatureSet, FeatureScopeEnum, FeatureTypeEnum
from django_pim.services import feature_set_service as svc

from .factories import FeatureFactory, FeatureInFeatureSetFactory, FeatureSetFactory


def _feature(idx: str, *, required: bool = False, scope: int = FeatureScopeEnum.BUSINESS_UNIT):
    return FeatureFactory(idx=idx, is_required=required, scope=scope, feature_type=FeatureTypeEnum.DECIMAL)


@pytest.mark.django_db
class TestEffectiveFlag:
    @pytest.mark.parametrize(
        ("feature_flag", "override", "expected"),
        [
            (False, None, False),
            (True, None, True),
            (False, True, True),
            (True, False, False),
            (True, True, True),
            (False, False, False),
        ],
    )
    def test_truth_table(self, feature_flag, override, expected):
        membership = FeatureInFeatureSetFactory(
            feature=_feature("voltage", required=feature_flag), is_required=override
        )

        assert membership.effective_is_required is expected

    def test_override_defaults_to_none_meaning_inherit(self):
        membership = FeatureInFeatureSetFactory(feature=_feature("voltage", required=True))

        assert membership.is_required is None

    def test_queryset_filter_matches_property(self):
        combos = itertools.product([False, True], [None, False, True])
        memberships = [
            FeatureInFeatureSetFactory(feature=_feature(f"f{i}", required=ff), is_required=ov)
            for i, (ff, ov) in enumerate(combos)
        ]

        from_sql = set(FeatureInFeatureSet.objects.effective_required().values_list("pk", flat=True))

        assert from_sql == {m.pk for m in memberships if m.effective_is_required}


@pytest.mark.django_db
class TestSystemScopeRejectsOverride:
    def test_save_with_override_on_system_feature_raises_value_error(self):
        system = _feature("name", scope=FeatureScopeEnum.SYSTEM)

        with pytest.raises(ValueError, match="system"):
            FeatureInFeatureSetFactory(feature=system, is_required=True)

    def test_save_without_override_on_system_feature_is_fine(self):
        system = _feature("name", required=True, scope=FeatureScopeEnum.SYSTEM)

        assert FeatureInFeatureSetFactory(feature=system).pk

    def test_service_rejects_override_on_system_feature(self):
        system = _feature("name", scope=FeatureScopeEnum.SYSTEM)
        fs = FeatureSetFactory(idx="s")
        FeatureInFeatureSetFactory(feature_set=fs, feature=system)

        with pytest.raises(ValueError, match="system"):
            svc.set_feature_required_override("s", "name", True)


@pytest.mark.django_db
class TestOverrideService:
    def test_set_true_false_none(self):
        fs = FeatureSetFactory(idx="battery")
        feature = _feature("voltage")
        membership = FeatureInFeatureSetFactory(feature_set=fs, feature=feature)

        svc.set_feature_required_override("battery", "voltage", True)
        membership.refresh_from_db()
        assert membership.is_required is True
        svc.set_feature_required_override("battery", "voltage", False)
        membership.refresh_from_db()
        assert membership.is_required is False
        svc.set_feature_required_override("battery", "voltage", None)
        membership.refresh_from_db()
        assert membership.is_required is None

    def test_does_not_move_position(self):
        fs = FeatureSetFactory(idx="battery")
        first = FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("a"), position=500)
        FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("b"), position=700)

        svc.set_feature_required_override("battery", "a", True)

        first.refresh_from_db()
        assert first.position == 500

    def test_unknown_membership_raises_does_not_exist(self):
        FeatureSetFactory(idx="battery")
        _feature("voltage")

        with pytest.raises(FeatureInFeatureSet.DoesNotExist):
            svc.set_feature_required_override("battery", "voltage", True)

    def test_detaching_the_feature_removes_the_override(self):
        fs = FeatureSetFactory(idx="battery")
        feature = _feature("voltage")
        FeatureInFeatureSetFactory(feature_set=fs, feature=feature, is_required=True)

        svc.bulk_remove_features_from_set("battery", ["voltage"])
        svc.bulk_add_features_to_set("battery", [{"feature_idx": "voltage"}])

        assert FeatureInFeatureSet.objects.get(feature_set=fs, feature=feature).is_required is None

    def test_bulk_add_accepts_is_required(self):
        FeatureSetFactory(idx="battery")
        _feature("voltage")
        _feature("cell_count", required=True)

        rows = svc.bulk_add_features_to_set(
            "battery",
            [{"feature_idx": "voltage", "is_required": True}, {"feature_idx": "cell_count", "is_required": False}],
        )

        assert [r.is_required for r in rows] == [True, False]

    def test_bulk_add_without_key_inherits(self):
        FeatureSetFactory(idx="battery")
        _feature("voltage")

        (row,) = svc.bulk_add_features_to_set("battery", [{"feature_idx": "voltage"}])

        assert row.is_required is None

    def test_reorder_keeps_override(self):
        fs = FeatureSetFactory(idx="battery")
        membership = FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("voltage"), is_required=True)

        svc.reorder_features_in_set("battery", [{"feature_idx": "voltage", "position": 900}])

        membership.refresh_from_db()
        assert (membership.position, membership.is_required) == (900, True)


@pytest.mark.django_db
class TestRequiredSet:
    def test_union_of_feature_flag_override_and_system(self):
        fs = FeatureSetFactory(idx="battery")
        FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("from_feature", required=True))
        FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("from_set"), is_required=True)
        FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("optional"))
        _feature("name", required=True, scope=FeatureScopeEnum.SYSTEM)
        _feature("subname", required=False, scope=FeatureScopeEnum.SYSTEM)

        result = {feature.idx: source for feature, source in svc.get_required_features("battery")}

        assert result == {"name": "system", "from_feature": "feature", "from_set": "feature_set"}

    def test_override_true_wins_even_when_feature_is_required(self):
        fs = FeatureSetFactory(idx="battery")
        FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("v", required=True), is_required=True)

        assert [(f.idx, s) for f, s in svc.get_required_features("battery")] == [("v", "feature_set")]

    def test_override_false_un_requires(self):
        fs = FeatureSetFactory(idx="cable")
        FeatureInFeatureSetFactory(feature_set=fs, feature=_feature("voltage", required=True), is_required=False)

        assert svc.get_required_features("cable") == []

    def test_no_leak_between_sets(self):
        voltage = _feature("voltage", required=True)
        battery, cable = FeatureSetFactory(idx="battery"), FeatureSetFactory(idx="cable")
        FeatureInFeatureSetFactory(feature_set=battery, feature=voltage)
        FeatureInFeatureSetFactory(feature_set=cable, feature=voltage, is_required=False)

        assert [f.idx for f, _ in svc.get_required_features("battery")] == ["voltage"]
        assert svc.get_required_features("cable") == []

    def test_system_feature_membership_row_is_reported_once_as_system(self):
        fs = FeatureSetFactory(idx="battery")
        system = _feature("name", required=True, scope=FeatureScopeEnum.SYSTEM)
        FeatureInFeatureSetFactory(feature_set=fs, feature=system)

        assert [(f.idx, s) for f, s in svc.get_required_features("battery")] == [("name", "system")]

    def test_unknown_set_raises(self):
        with pytest.raises(Exception, match="does not exist"):
            svc.get_required_features("nope")

    def test_by_set_map_is_sorted_and_includes_system_and_empty_sets(self):
        _feature("name", required=True, scope=FeatureScopeEnum.SYSTEM)
        battery, cable = FeatureSetFactory(idx="battery"), FeatureSetFactory(idx="cable")
        FeatureInFeatureSetFactory(feature_set=battery, feature=_feature("zz", required=True))
        FeatureInFeatureSetFactory(feature_set=battery, feature=_feature("aa"), is_required=True)
        FeatureInFeatureSetFactory(feature_set=cable, feature=_feature("mm", required=True), is_required=False)

        assert svc.required_feature_idxs_by_set() == {
            "battery": ["aa", "name", "zz"],
            "cable": ["name"],
        }
