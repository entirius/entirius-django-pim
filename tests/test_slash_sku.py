# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Slash-containing SKU support (e.g. "1C01/N", "2R04/NR").

`<path:sku>` URL converter + route ordering must keep every SKU-addressed route
resolvable for SKUs with a slash, without breaking non-slash SKUs or sub-routes.
Plus the `validate_routable_sku` guard. (The pim-fix-1 ProductAttribute NULL
constraint is covered in test_models.py.)
"""

import pytest
from django.urls import resolve

from django_pim.validators import RESERVED_SKU_SUFFIXES, validate_routable_sku

ADMIN = "/api/pim/v2/admin/default"

SLASH_SKUS = ["1C01/N", "2R04/NR"]
PLAIN_SKUS = ["ENT-S001", "1C01"]


class TestSlashSkuRouting:
    """resolve() must land on the right view with the full SKU in kwargs (no DB)."""

    @pytest.mark.parametrize("sku", SLASH_SKUS + PLAIN_SKUS)
    def test_product_detail(self, sku):
        match = resolve(f"{ADMIN}/products/{sku}/")
        assert match.url_name == "product-detail"
        assert match.kwargs["sku"] == sku

    @pytest.mark.parametrize("sku", SLASH_SKUS + PLAIN_SKUS)
    @pytest.mark.parametrize(
        "suffix,expected",
        [
            ("pictures/", "productpicture-list"),
            ("links/", "productlink-list"),
            ("files/", "productfile-list"),
            ("videos/", "productvideo-list"),
            ("copy-attributes/", "product-copy-attributes"),
            ("add-to-channel/", "product-add-to-channel"),
            ("toggle-override/", "product-toggle-override"),
        ],
    )
    def test_product_subroutes(self, sku, suffix, expected):
        match = resolve(f"{ADMIN}/products/{sku}/{suffix}")
        assert match.url_name == expected
        assert match.kwargs["sku"] == sku

    @pytest.mark.parametrize("sku", SLASH_SKUS + PLAIN_SKUS)
    def test_nested_pk_subroute(self, sku):
        # Greedy <path:sku> must not eat the trailing /<pk>/.
        match = resolve(f"{ADMIN}/products/{sku}/pictures/42/")
        assert match.url_name == "productpicture-detail"
        assert match.kwargs["sku"] == sku
        assert match.kwargs["pk"] == 42

    def test_bulk_literal_not_shadowed(self):
        match = resolve(f"{ADMIN}/products/bulk/")
        assert match.url_name == "product-bulk-update"


class TestValidateRoutableSku:
    def test_plain_and_slash_suffix_accepted(self):
        for sku in ["PROD-001", "1C01/N", "2R04/NR", "AB/pictures/CD"]:
            validate_routable_sku(sku)  # must not raise

    @pytest.mark.parametrize(
        "sku",
        [
            "1C01/files",
            "X/pictures",
            "Y/links/5",
            "Z/copy-attributes",
            "W/links/42",
            "A/edit",
            "B/videos",
            "C/copy-translations",
            "D/toggle-media-override",
            "E/history",
            "F/force-repush",
            "G/set-preferred-supplier",
        ],
    )
    def test_reserved_tail_rejected(self, sku):
        with pytest.raises(ValueError):
            validate_routable_sku(sku)

    def test_bulk_whole_sku_rejected(self):
        # "bulk" (no slash) collides with the sibling products/bulk/ route.
        with pytest.raises(ValueError):
            validate_routable_sku("bulk")

    def test_message_names_the_reserved_word(self):
        with pytest.raises(ValueError, match="files"):
            validate_routable_sku("1C01/files")

    def test_covers_all_module_subroutes(self):
        assert {"pictures", "links", "files", "videos", "edit", "history", "changes"} <= RESERVED_SKU_SUFFIXES
