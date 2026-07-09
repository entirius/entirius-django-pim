# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import logging

from slugify import slugify

from ..models import Attribute
from ..utils.t9n import t9n_cleanup, t9n_update

logger = logging.getLogger(__name__)


class AttributeManager:
    IDX_REPLACEMENTS = (
        (">=", " greather-equal-than "),
        ("<=", " less-equal-than "),
        ("<", " less-than "),
        (">", " greather-than "),
        ("|", " or "),
        ("%", " percent "),
        (r"\,", "comma"),
        (r"\.", "dot"),
    )

    _cache_attributes = {}

    def generate_idx(name):
        HASHLEN = 8  # dlugosc hasha
        separator = "_"
        name = name.strip()
        name = name.lower()
        idx = slugify(name, replacements=AttributeManager.IDX_REPLACEMENTS, separator=separator)
        if len(idx) > Attribute.MAX_IDX_LENGTH:
            prefix = idx[: Attribute.MAX_IDX_LENGTH - HASHLEN - 1]
            rest = idx[Attribute.MAX_IDX_LENGTH - HASHLEN - 1 :]
            rest = rest.encode("utf-8")
            m = hashlib.md5()
            m.update(rest)
            h = m.hexdigest()
            idx = "%s%s%s" % (prefix, separator, h[:HASHLEN])
        Attribute.validate_idx(idx)
        return idx

    def get_attribute(feature, idx):
        query = Attribute.objects.filter(feature=feature, idx=idx)
        return query.first()

    def get_or_create_attribute(idx, feature, name_t9n=None):
        feature_idx = feature.idx
        if feature_idx not in AttributeManager._cache_attributes:
            AttributeManager._cache_attributes[feature_idx] = {}
        if idx in AttributeManager._cache_attributes[feature_idx]:
            return AttributeManager._cache_attributes[feature_idx][idx], False

        if name_t9n is not None:
            name_t9n = t9n_cleanup(name_t9n)
        attribute = Attribute.objects.filter(idx=idx).first()
        if attribute is None:
            created = True
            attribute = Attribute(idx=idx, name_t9n=name_t9n)
            attribute.save()
            logger.info("New Attribute: [%s]", idx)
        else:
            created = False
            AttributeManager.update_attribute(attribute=attribute, name_t9n=name_t9n)
        feature.attributes.add(attribute)
        AttributeManager._cache_attributes[feature_idx][idx] = attribute
        return (attribute, created)

    def update_attribute(attribute, name_t9n=None):
        updated = []
        to_save = False
        if name_t9n is not None:
            is_t9n_updated, changed = t9n_update(attribute.name_t9n, name_t9n)
            if is_t9n_updated:
                to_save = True
                updated.append("name_t9n: %s" % changed)
        if to_save:
            attribute.save()
            logger.info("Attribute [%s] updated fields: (%s)", attribute.idx, ", ".join(updated))
