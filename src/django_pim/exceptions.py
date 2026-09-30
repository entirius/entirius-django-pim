# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Domain exceptions raised by the PIM service layer.

Deliberately NOT ``ValueError`` subclasses: callers of ``create_product`` commonly treat any
``ValueError`` as "duplicate SKU", and these two mean something else.
"""


class RequiredFeaturesMissingError(Exception):
    """A product was created on a feature set without every required feature's value."""

    def __init__(self, feature_set_idx: str, missing_feature_idxs: list[str]) -> None:
        self.feature_set_idx = feature_set_idx
        self.missing_feature_idxs = sorted(missing_feature_idxs)
        super().__init__(f"Feature set '{feature_set_idx}' requires values for: {', '.join(self.missing_feature_idxs)}")


class UnresolvedAttributesError(Exception):
    """Strict create: the payload references features, options or categories that do not exist.

    ``unresolved_attributes`` holds feature idxs (unknown feature, or a feature whose option idx
    is unknown / belongs to another feature); ``unknown_category_idxs`` the unknown category idxs.
    """

    def __init__(self, unresolved_attributes: list[str], unknown_category_idxs: list[str]) -> None:
        self.unresolved_attributes = sorted(set(unresolved_attributes))
        self.unknown_category_idxs = sorted(set(unknown_category_idxs))
        parts = []
        if self.unresolved_attributes:
            parts.append(f"attributes: {', '.join(self.unresolved_attributes)}")
        if self.unknown_category_idxs:
            parts.append(f"categories: {', '.join(self.unknown_category_idxs)}")
        super().__init__(f"Unresolved references ({'; '.join(parts)})")
