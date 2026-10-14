# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The PIM adapter against the shared enrichment adapter conformance kit.

Targets: `attribute_value` text, select and multiselect, and `video`. The kit is test-only
(`entirius-django-enrichment` sits in the `test` extra); the adapter itself still imports nothing from it.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_enrichment.testing.adapter_conformance import (
    AdapterConformance,
    ConformanceCase,
    FieldCatalogConformance,
)

from django_pim.models import FeatureTypeEnum, ProductAttribute
from django_pim.services import enrichment_adapter, product_file_service

from .factories import (
    AttributeFactory,
    ChannelFactory,
    FeatureFactory,
    FeatureInFeatureSetFactory,
    FeatureSetFactory,
    LanguageFactory,
    ProductFactory,
    RealProductFactory,
)

SKU = "CONF-1"


def _channel():
    channel = ChannelFactory(is_default=True)
    channel.languages.add(LanguageFactory(iso2="EN", iso3="ENG"))
    return channel


def _product_with(channel, feature):
    product = ProductFactory(shop=channel, real_product=RealProductFactory(sku=SKU), feature_set=FeatureSetFactory())
    FeatureInFeatureSetFactory(feature_set=product.feature_set, feature=feature)
    return product


def _select_feature(idx: str, feature_type: int, options: tuple[str, ...]):
    feature = FeatureFactory(idx=idx, feature_type=feature_type, name_t9n={"pl": idx.title()})
    for position, option in enumerate(options):
        AttributeFactory(feature=feature, idx=option, name_t9n={"pl": option.title()}, display_order=position)
    return feature


def _case(channel, feature_idx: str, language: str | None, values: tuple[dict, dict]) -> ConformanceCase:
    locator = enrichment_adapter.make_locator(field_key=feature_idx, channel=channel.idx, language=language)
    return ConformanceCase(SKU, "attribute_value", locator, *values)


def _text_case(channel) -> ConformanceCase:
    feature = FeatureFactory(idx="conf_desc", feature_type=FeatureTypeEnum.TEXT_T9N, name_t9n={"pl": "Opis"})
    product = _product_with(channel, feature)
    ProductAttribute.objects.create(product=product, feature=feature, value_txt_t9n={"pl": "stary", "en": "old"})
    return _case(channel, "conf_desc", "pl", ({"text": "nowy"}, {"text": "edited elsewhere"}))


def _select_case(channel) -> ConformanceCase:
    _product_with(channel, _select_feature("conf_color", FeatureTypeEnum.SELECT, ("red", "blue")))
    return _case(channel, "conf_color", None, ({"option": "red"}, {"option": "blue"}))


def _multiselect_case(channel) -> ConformanceCase:
    _product_with(channel, _select_feature("conf_tags", FeatureTypeEnum.MULTISELECT, ("cotton", "eco", "wool")))
    return _case(channel, "conf_tags", None, ({"options": ["eco", "wool"]}, {"options": ["cotton"]}))


_ATTRIBUTE_CASES = {"text": _text_case, "select": _select_case, "multiselect": _multiselect_case}


@pytest.fixture
def adapter():
    return enrichment_adapter


@pytest.fixture(params=sorted(_ATTRIBUTE_CASES))
def conformance_case(request, db) -> ConformanceCase:
    return _ATTRIBUTE_CASES[request.param](_channel())


@pytest.fixture
def catalog_channel(db) -> str:
    channel = _channel()
    FeatureFactory(idx="conf_name", feature_type=FeatureTypeEnum.VARCHAR255_T9N, name_t9n={"pl": "Nazwa"})
    FeatureFactory(idx="conf_body", feature_type=FeatureTypeEnum.TEXT_T9N, name_t9n={"pl": "Opis"})
    _select_feature("conf_color", FeatureTypeEnum.SELECT, ("red", "blue"))
    _select_feature("conf_tags", FeatureTypeEnum.MULTISELECT, ("eco",))
    return channel.idx


class TestPimAdapterConformance(AdapterConformance, FieldCatalogConformance):
    pass


# --- video: the bus stages the binary and records `applied_snapshot`; a stand-in does both here ---------------


def _video(payload: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile("staged.mp4", b"\x00\x00\x00\x18ftypmp42" + payload, content_type="video/mp4")


class _VideoBus:
    """The PIM adapter plus what `apply_service` does around a video apply: stage the next payload as the
    proposal's binary and record the post-apply value as `applied_snapshot` (what `revert` diffs)."""

    def __init__(self, payloads: list[bytes]):
        self._payloads = payloads

    def __getattr__(self, name: str):
        return getattr(enrichment_adapter, name)

    def apply(self, proposal) -> None:
        staged = _video(self._payloads.pop(0))
        proposal.open_staged_file = lambda: staged
        enrichment_adapter.apply(proposal)
        proposal.applied_snapshot = enrichment_adapter.read_current(
            subject_ref=proposal.subject_ref, target_kind=proposal.target_kind, target_locator=proposal.target_locator
        )


_VIDEO_PAYLOADS = [b"video-a", b"video-b"]


def _stored_name(payload: bytes) -> str:
    """Upload ahead (unlinked) so the case knows the stored name; apply then dedups onto this row."""
    return product_file_service.upload_file(_video(payload), file_type="video").file.name


class TestPimVideoConformance(AdapterConformance):
    @pytest.fixture
    def adapter(self):
        return _VideoBus(list(_VIDEO_PAYLOADS))

    @pytest.fixture
    def conformance_case(self, db) -> ConformanceCase:
        channel = _channel()
        ProductFactory(shop=channel, real_product=RealProductFactory(sku=SKU), feature_set=FeatureSetFactory())
        first, second = (_stored_name(payload) for payload in _VIDEO_PAYLOADS)
        return ConformanceCase(
            SKU, "video", {"channel": channel.idx}, {"files": [first]}, {"files": sorted([first, second])}
        )
