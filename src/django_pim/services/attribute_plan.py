# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Plan-then-write for product attribute payloads.

``plan_product_attributes`` resolves features and options and decides what would be stored,
without touching the database beyond two reads. ``write_planned_attributes`` performs the
writes. ``create_product`` checks required features and strict references against the plan so
the check sees exactly what the write step will store.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from ..models import Attribute, Feature, FeatureTypeEnum, Product, ProductAttribute
from .gap_check_registry import _is_empty

_SELECT_TYPES = (FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT)
_DECIMAL_TYPES = (
    FeatureTypeEnum.DECIMAL,
    FeatureTypeEnum.TEMPERATURE,
    FeatureTypeEnum.LENGTH,
    FeatureTypeEnum.MASS,
)
_TEXT_TYPES = (FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT)
_T9N_TYPES = (FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N)
_JSON_TYPES = (FeatureTypeEnum.JSON, FeatureTypeEnum.JSON_T9N)


@dataclass(frozen=True)
class PlannedFeature:
    """One feature touched by the payload: its existing rows are replaced by ``rows``.

    ``rows`` are ``ProductAttribute`` kwargs (without ``product``). An empty list is a SELECT /
    MULTISELECT clear signal.
    """

    feature: Feature
    rows: list[dict]

    def is_supplied(self) -> bool:
        return any(_row_is_supplied(self.feature, row) for row in self.rows)


@dataclass
class AttributePlan:
    planned: list[PlannedFeature] = field(default_factory=list)
    unresolved: set[str] = field(default_factory=set)

    def supplied_feature_idxs(self) -> set[str]:
        return {p.feature.idx for p in self.planned if p.is_supplied()}


def has_attribute_value(attr_data: dict, feature_type: int) -> bool:
    """Check if the attribute data carries a value for the given type.

    For SELECT/MULTISELECT, key presence means "process this" (even if null/empty
    — that signals deletion). For other types, an explicit None means "set".
    """
    if feature_type == FeatureTypeEnum.MULTISELECT:
        return "attribute_idxs" in attr_data
    if feature_type == FeatureTypeEnum.SELECT:
        return "attribute_idx" in attr_data
    if feature_type == FeatureTypeEnum.BOOL:
        return attr_data.get("value_bool") is not None
    if feature_type in _DECIMAL_TYPES:
        return attr_data.get("value_decimal") is not None
    if feature_type in _TEXT_TYPES:
        return attr_data.get("value_txt") is not None
    if feature_type in _T9N_TYPES:
        return attr_data.get("value_txt_t9n") is not None
    if feature_type in _JSON_TYPES:
        return attr_data.get("value_json") is not None
    if feature_type == FeatureTypeEnum.DATETIME:
        return attr_data.get("value_datetime") is not None
    return False


def _row_is_supplied(feature: Feature, row: dict) -> bool:
    """A stored row satisfies a requirement when it carries a non-empty value.

    Same emptiness rule as the gap checks: bool ``False`` and decimal ``0`` are values.
    """
    if feature.feature_type in _SELECT_TYPES:
        return row.get("attribute") is not None
    value = next((v for k, v in row.items() if k.startswith("value_")), None)
    if isinstance(value, dict):
        if feature.feature_type in _T9N_TYPES:
            return any(not _is_empty(v) for v in value.values())
        return bool(value)
    return not _is_empty(value)


def _scalar_row(feature: Feature, attr_data: dict) -> dict:
    row: dict = {"feature": feature}
    feature_type = feature.feature_type
    if feature_type == FeatureTypeEnum.BOOL:
        row["value_bool"] = attr_data.get("value_bool")
    elif feature_type in _DECIMAL_TYPES:
        row["value_decimal"] = Decimal(str(attr_data["value_decimal"]))
    elif feature_type in _TEXT_TYPES:
        row["value_txt"] = attr_data["value_txt"]
    elif feature_type in _T9N_TYPES:
        row["value_txt_t9n"] = attr_data["value_txt_t9n"]
    elif feature_type in _JSON_TYPES:
        row["value_json"] = attr_data["value_json"]
    elif feature_type == FeatureTypeEnum.DATETIME:
        row["value_datetime"] = attr_data["value_datetime"]
    return row


def _requested_option_idxs(attr_data: dict, feature: Feature) -> list[str]:
    if feature.feature_type == FeatureTypeEnum.MULTISELECT:
        return list(attr_data.get("attribute_idxs") or [])
    idx = attr_data.get("attribute_idx")
    return [idx] if idx else []


def _load_options(planned_inputs: list[tuple[dict, Feature]]) -> dict[tuple[int, str], Attribute]:
    lookups = {
        (feature.pk, idx)
        for attr_data, feature in planned_inputs
        if feature.feature_type in _SELECT_TYPES
        for idx in _requested_option_idxs(attr_data, feature)
    }
    if not lookups:
        return {}
    options = Attribute.objects.filter(feature_id__in={fk for fk, _ in lookups}, idx__in={idx for _, idx in lookups})
    return {(option.feature_id, option.idx): option for option in options}


def plan_product_attributes(attributes: list[dict]) -> AttributePlan:
    """Resolve features and options and decide what a write would store. Reads only.

    Features with no value for their type (or unknown) are left out of ``planned`` — the write
    step leaves their existing rows untouched. Unknown features and unknown / foreign options
    are recorded in ``unresolved`` (by feature idx) and dropped from the rows.
    """
    features_by_idx = {f.idx: f for f in Feature.objects.filter(idx__in=[a["feature_idx"] for a in attributes])}
    plan = AttributePlan(unresolved={a["feature_idx"] for a in attributes if a["feature_idx"] not in features_by_idx})
    inputs = [
        (attr_data, features_by_idx[attr_data["feature_idx"]])
        for attr_data in attributes
        if attr_data["feature_idx"] in features_by_idx
        and has_attribute_value(attr_data, features_by_idx[attr_data["feature_idx"]].feature_type)
    ]
    options = _load_options(inputs)
    for attr_data, feature in inputs:
        if feature.feature_type not in _SELECT_TYPES:
            plan.planned.append(PlannedFeature(feature, [_scalar_row(feature, attr_data)]))
            continue
        rows = []
        for idx in _requested_option_idxs(attr_data, feature):
            if (option := options.get((feature.pk, idx))) is None:
                plan.unresolved.add(feature.idx)
            else:
                rows.append({"feature": feature, "attribute": option})
        plan.planned.append(PlannedFeature(feature, rows))
    return plan


def write_planned_attributes(product: Product, plan: AttributePlan) -> None:
    """Replace the product's rows for every planned feature (bulk delete + one bulk_create).

    ``bulk_create`` skips post_save signals — callers trigger Matrix sync themselves.
    """
    if not plan.planned:
        return
    ProductAttribute.objects.filter(product=product, feature__in=[p.feature for p in plan.planned]).delete()
    new_rows = [ProductAttribute(product=product, **row) for p in plan.planned for row in p.rows]
    if new_rows:
        ProductAttribute.objects.bulk_create(new_rows)
