# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the referential enrichment adapter (etap-04).

The adapter is the PIM read/write boundary the enrichment bus routes through. These tests exercise
it directly (no bus, no django-enrichment dependency) and pin the two non-obvious contracts:
read-merge-write (never lose sibling languages) and inheritance-aware override.
"""

import io
import os
from unittest import mock

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from django_pim import models
from django_pim.models import (
    AttributePicture,
    FeatureTypeEnum,
    Picture,
    PictureRoleEnum,
    ProductAttribute,
    ProductPicture,
)
from django_pim.services import enrichment_adapter, gap_detection_service, product_picture_service

from .factories import (
    AttributeFactory,
    ChannelFactory,
    FeatureFactory,
    FeatureSetFactory,
    GapDefinitionFactory,
    GapExemptionFactory,
    GapFindingFactory,
    LanguageFactory,
    ProductCategoryFactory,
    ProductFactory,
    ProductInCategoryFactory,
    RealProductFactory,
)


def _image(name="img.png", color="red"):
    """In-memory PNG for picture-adapter tests (distinct colours → distinct SHA1)."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=color).save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/png")


def _make_product(*, channel, sku, feature_idx="enr_desc", t9n=None, feature_type=FeatureTypeEnum.TEXT_T9N):
    feature = FeatureFactory(idx=feature_idx, feature_type=feature_type)
    real_product = RealProductFactory(sku=sku)
    product = ProductFactory(shop=channel, real_product=real_product, feature_set=FeatureSetFactory())
    if t9n is not None:
        ProductAttribute.objects.create(product=product, feature=feature, value_txt_t9n=t9n)
    return product, feature


def _locator(channel, language="pl", feature_idx="enr_desc"):
    return {"channel": channel.idx, "language": language, "feature_idx": feature_idx}


@pytest.mark.django_db
class TestReadCurrent:
    def test_returns_raw_language_value(self):
        channel = ChannelFactory(is_default=True)
        _make_product(channel=channel, sku="SKU-R1", t9n={"pl": "opis-pl", "en": "desc-en"})

        snap = enrichment_adapter.read_current(
            subject_ref="SKU-R1", target_kind="attribute_value", target_locator=_locator(channel, "pl")
        )

        assert snap == {"text": "opis-pl"}

    def test_missing_language_is_empty(self):
        channel = ChannelFactory(is_default=True)
        _make_product(channel=channel, sku="SKU-R2", t9n={"pl": "opis-pl"})

        snap = enrichment_adapter.read_current(
            subject_ref="SKU-R2", target_kind="attribute_value", target_locator=_locator(channel, "de")
        )

        assert snap == {"text": ""}

    def test_missing_product_is_empty(self):
        channel = ChannelFactory(is_default=True)

        snap = enrichment_adapter.read_current(
            subject_ref="NOPE", target_kind="attribute_value", target_locator=_locator(channel, "pl")
        )

        assert snap == {"text": ""}


class _Proposal:
    """Minimal stand-in for ContentProposal — the adapter only reads a few attributes."""

    def __init__(
        self,
        *,
        subject_ref,
        target_locator,
        proposed_value=None,
        current_snapshot=None,
        applied_snapshot=None,
        target_kind="attribute_value",
        staged_image=None,
    ):
        self.subject_ref = subject_ref
        self.target_locator = target_locator
        self.proposed_value = proposed_value or {}
        self.current_snapshot = current_snapshot or {}
        self.applied_snapshot = applied_snapshot or {}
        self.target_kind = target_kind
        self._staged_image = staged_image

    def open_staged_file(self):
        """Mirror ContentProposal.open_staged_file — hand the adapter the staged binary (media)."""
        return self._staged_image


@pytest.mark.django_db
class TestApply:
    def test_apply_merges_without_losing_other_languages(self):
        channel = ChannelFactory(is_default=True)
        product, feature = _make_product(channel=channel, sku="SKU-A1", t9n={"pl": "stary", "en": "old-en"})
        proposal = _Proposal(
            subject_ref="SKU-A1", target_locator=_locator(channel, "pl"), proposed_value={"text": "nowy"}
        )

        enrichment_adapter.apply(proposal)

        attr = ProductAttribute.objects.get(product=product, feature=feature)
        assert attr.value_txt_t9n == {"pl": "nowy", "en": "old-en"}

    def test_apply_creates_attribute_when_absent(self):
        channel = ChannelFactory(is_default=True)
        product, feature = _make_product(channel=channel, sku="SKU-A2")  # no attribute yet
        proposal = _Proposal(
            subject_ref="SKU-A2", target_locator=_locator(channel, "en"), proposed_value={"text": "fresh"}
        )

        enrichment_adapter.apply(proposal)

        attr = ProductAttribute.objects.get(product=product, feature=feature)
        assert attr.value_txt_t9n == {"en": "fresh"}

    def test_apply_on_default_channel_sets_no_override(self):
        channel = ChannelFactory(is_default=True)
        product, feature = _make_product(channel=channel, sku="SKU-A3", t9n={"pl": "x"})
        proposal = _Proposal(subject_ref="SKU-A3", target_locator=_locator(channel, "pl"), proposed_value={"text": "y"})

        enrichment_adapter.apply(proposal)

        attr = ProductAttribute.objects.get(product=product, feature=feature)
        assert attr.overridden_langs == []

    def test_apply_on_inheriting_secondary_channel_marks_override(self):
        channel = ChannelFactory(is_default=False, inheritance_enabled=True)
        product, feature = _make_product(channel=channel, sku="SKU-A4", t9n={"pl": "x"})
        product.inherit_attributes = True  # enr_desc is not a description feature -> attributes branch
        product.save(update_fields=["inherit_attributes"])
        proposal = _Proposal(subject_ref="SKU-A4", target_locator=_locator(channel, "pl"), proposed_value={"text": "y"})

        enrichment_adapter.apply(proposal)

        attr = ProductAttribute.objects.get(product=product, feature=feature)
        assert attr.overridden_langs == ["pl"]

    def test_apply_rejects_non_t9n_feature(self):
        channel = ChannelFactory(is_default=True)
        _make_product(channel=channel, sku="SKU-A5", feature_idx="enr_weight", feature_type=FeatureTypeEnum.DECIMAL)
        proposal = _Proposal(
            subject_ref="SKU-A5",
            target_locator=_locator(channel, "pl", feature_idx="enr_weight"),
            proposed_value={"text": "y"},
        )

        with pytest.raises(ValueError, match="translatable text only"):
            enrichment_adapter.apply(proposal)

    def test_apply_rejects_non_string_text(self):
        channel = ChannelFactory(is_default=True)
        _make_product(channel=channel, sku="SKU-A6", t9n={"pl": "x"})
        proposal = _Proposal(
            subject_ref="SKU-A6", target_locator=_locator(channel, "pl"), proposed_value={"text": {"nested": 1}}
        )

        with pytest.raises(ValueError, match="expects a string value"):
            enrichment_adapter.apply(proposal)

    def test_apply_missing_text_key_raises_value_error(self):
        channel = ChannelFactory(is_default=True)
        _make_product(channel=channel, sku="SKU-A7", t9n={"pl": "x"})
        proposal = _Proposal(subject_ref="SKU-A7", target_locator=_locator(channel, "pl"), proposed_value={})

        with pytest.raises(ValueError, match="expects a string value"):
            enrichment_adapter.apply(proposal)


@pytest.mark.django_db
class TestRevert:
    def test_revert_restores_snapshot_value(self):
        channel = ChannelFactory(is_default=True)
        product, feature = _make_product(channel=channel, sku="SKU-V1", t9n={"pl": "current", "en": "keep-en"})
        proposal = _Proposal(
            subject_ref="SKU-V1", target_locator=_locator(channel, "pl"), current_snapshot={"text": "original"}
        )

        enrichment_adapter.revert(proposal)

        attr = ProductAttribute.objects.get(product=product, feature=feature)
        assert attr.value_txt_t9n == {"pl": "original", "en": "keep-en"}


def _fs_proposal(channel, *, sku, proposed_value=None, current_snapshot=None):
    return _Proposal(
        subject_ref=sku,
        target_locator={"channel": channel.idx},
        target_kind="feature_set",
        proposed_value=proposed_value,
        current_snapshot=current_snapshot,
    )


@pytest.mark.django_db
class TestReadCurrentFeatureSet:
    def test_returns_current_set_idx(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="FS-R1")

        snap = enrichment_adapter.read_current(
            subject_ref="FS-R1", target_kind="feature_set", target_locator={"channel": channel.idx}
        )

        assert snap == {"featureset_idx": product.feature_set.idx}

    def test_missing_product_is_empty(self):
        channel = ChannelFactory(is_default=True)

        snap = enrichment_adapter.read_current(
            subject_ref="FS-NOPE", target_kind="feature_set", target_locator={"channel": channel.idx}
        )

        assert snap == {"featureset_idx": ""}

    def test_reflects_live_change_for_drift(self):
        # The bus's drift check is `read_current != current_snapshot` — prove the adapter side moves.
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="FS-R2")
        locator = {"channel": channel.idx}
        snapshot = enrichment_adapter.read_current(
            subject_ref="FS-R2", target_kind="feature_set", target_locator=locator
        )
        assert snapshot == {"featureset_idx": product.feature_set.idx}  # the "before" state is pinned

        product.feature_set = FeatureSetFactory(idx="fs-moved")
        product.save(update_fields=["feature_set"])

        live = enrichment_adapter.read_current(subject_ref="FS-R2", target_kind="feature_set", target_locator=locator)
        assert live != snapshot
        assert live == {"featureset_idx": "fs-moved"}


@pytest.mark.django_db
class TestApplyFeatureSet:
    def test_apply_switches_set(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="FS-A1")
        target = FeatureSetFactory(idx="fs-real")

        enrichment_adapter.apply(_fs_proposal(channel, sku="FS-A1", proposed_value={"featureset_idx": "fs-real"}))

        product.refresh_from_db()
        assert product.feature_set == target

    def test_unknown_idx_raises(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="FS-A2")

        with pytest.raises(ValueError, match="unknown featureset_idx"):
            enrichment_adapter.apply(_fs_proposal(channel, sku="FS-A2", proposed_value={"featureset_idx": "ghost"}))

    def test_missing_idx_raises(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="FS-A3")

        with pytest.raises(ValueError, match="non-empty featureset_idx"):
            enrichment_adapter.apply(_fs_proposal(channel, sku="FS-A3", proposed_value={}))

    def test_non_string_idx_raises(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="FS-A4")

        with pytest.raises(ValueError, match="non-empty featureset_idx"):
            enrichment_adapter.apply(_fs_proposal(channel, sku="FS-A4", proposed_value={"featureset_idx": 42}))

    def test_missing_product_raises_object_does_not_exist(self):
        # Pin the exception type: the bus (apply_service) catches ObjectDoesNotExist and rewrites
        # it to the sanitized target-missing error — changing this type is a conscious decision.
        channel = ChannelFactory(is_default=True)
        FeatureSetFactory(idx="fs-orphan")

        with pytest.raises(ObjectDoesNotExist):
            enrichment_adapter.apply(
                _fs_proposal(channel, sku="FS-GHOST", proposed_value={"featureset_idx": "fs-orphan"})
            )

    def test_apply_enqueues_gap_recompute(self):
        # The cascade trigger: apply uses `save(update_fields=["feature_set"])`, NOT a silent
        # `.update()`, so the gap post_save handler fires and the findings get recomputed.
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="FS-A5")
        FeatureSetFactory(idx="fs-cascade")

        with (
            mock.patch("django_pim.signals.handlers.is_gaps_enabled", return_value=True),
            mock.patch("django_pim.signals.handlers.enqueue_gap_recompute") as enqueue,
        ):
            enrichment_adapter.apply(
                _fs_proposal(channel, sku="FS-A5", proposed_value={"featureset_idx": "fs-cascade"})
            )

        product.refresh_from_db()
        assert product.feature_set.idx == "fs-cascade"  # the write happened — the mock alone can't pass
        enqueue.assert_called_once_with(product.pk)


@pytest.mark.django_db
class TestRevertFeatureSet:
    def test_revert_restores_snapshot_set(self):
        channel = ChannelFactory(is_default=True)
        original = FeatureSetFactory(idx="fs-original")
        product = ProductFactory(shop=channel, real_product=RealProductFactory(sku="FS-V1"), feature_set=original)
        product.feature_set = FeatureSetFactory(idx="fs-applied")
        product.save(update_fields=["feature_set"])

        enrichment_adapter.revert(
            _fs_proposal(channel, sku="FS-V1", current_snapshot={"featureset_idx": "fs-original"})
        )

        product.refresh_from_db()
        assert product.feature_set == original

    def test_revert_empty_snapshot_raises(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="FS-V2")

        with pytest.raises(ValueError, match="non-empty featureset_idx"):
            enrichment_adapter.revert(_fs_proposal(channel, sku="FS-V2", current_snapshot={}))

    def test_revert_unknown_snapshot_idx_raises(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="FS-V3")

        with pytest.raises(ValueError, match="unknown featureset_idx"):
            enrichment_adapter.revert(
                _fs_proposal(channel, sku="FS-V3", current_snapshot={"featureset_idx": "does-not-exist"})
            )

    def test_release_undo_anchor_noop_for_feature_set(self):
        # Classification proposals carry no media — the GC hook must never touch them.
        channel = ChannelFactory(is_default=True)
        proposal = _fs_proposal(channel, sku="FS-GC", current_snapshot={"featureset_idx": "anything"})

        assert enrichment_adapter.release_undo_anchor(proposal) == 0


@pytest.mark.django_db
class TestResolveTargets:
    def test_list_mode_echoes_refs(self):
        spec = {"mode": "list", "module": "pim", "channel": "c", "refs": ["A", "B"]}
        assert enrichment_adapter.resolve_targets(spec) == ["A", "B"]

    def test_filter_mode_returns_skus(self):
        channel = ChannelFactory(is_default=True)
        for sku in ("F1", "F2"):
            ProductFactory(shop=channel, real_product=RealProductFactory(sku=sku), feature_set=FeatureSetFactory())
        spec = {"mode": "filter", "module": "pim", "channel": channel.idx, "filters": {"is_enabled": False}}

        skus = enrichment_adapter.resolve_targets(spec)

        assert sorted(skus) == ["F1", "F2"]

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="unsupported scope mode"):
            enrichment_adapter.resolve_targets({"mode": "bogus", "module": "pim"})


@pytest.mark.django_db
class TestCategory:
    def test_read_current_returns_category_idxs(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="CAT-R1")
        ProductInCategoryFactory(product=product, category=ProductCategoryFactory(shop=channel, idx="cat-x"))

        snap = enrichment_adapter.read_current(
            subject_ref="CAT-R1", target_kind="category", target_locator={"channel": channel.idx}
        )
        assert snap == {"category_idxs": ["cat-x"]}

    def test_read_current_missing_product_empty(self):
        channel = ChannelFactory(is_default=True)
        snap = enrichment_adapter.read_current(
            subject_ref="NOPE", target_kind="category", target_locator={"channel": channel.idx}
        )
        assert snap == {"category_idxs": []}

    def test_apply_writes_categories(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="CAT-A1")
        ProductCategoryFactory(shop=channel, idx="cat-1")
        ProductCategoryFactory(shop=channel, idx="cat-2")

        enrichment_adapter.apply(
            _Proposal(
                subject_ref="CAT-A1",
                target_kind="category",
                target_locator={"channel": channel.idx},
                proposed_value={"category_idxs": ["cat-1", "cat-2"]},
            )
        )
        assert sorted(product.product_in_category.values_list("category__idx", flat=True)) == ["cat-1", "cat-2"]

    def test_apply_empty_raises(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="CAT-E1")
        with pytest.raises(ValueError, match="category apply requires"):
            enrichment_adapter.apply(
                _Proposal(
                    subject_ref="CAT-E1",
                    target_kind="category",
                    target_locator={"channel": channel.idx},
                    proposed_value={"category_idxs": []},
                )
            )

    def test_revert_restores_empty_snapshot(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="CAT-V1")
        ProductInCategoryFactory(product=product, category=ProductCategoryFactory(shop=channel, idx="cat-r"))

        enrichment_adapter.revert(
            _Proposal(
                subject_ref="CAT-V1",
                target_kind="category",
                target_locator={"channel": channel.idx},
                current_snapshot={"category_idxs": []},
            )
        )
        assert product.product_in_category.count() == 0


@pytest.mark.django_db
class TestFindGaps:
    def _rule(self, key="desc-rule", **kwargs):
        defaults = {
            "check_key": models.GapCheck.FEATURE_PRESENT,
            "severity": models.GapSeverity.CRITICAL,
            "params": {"feature_idx": "description"},
        }
        defaults.update(kwargs)
        return GapDefinitionFactory(key=key, **defaults)

    def _finding(self, *, channel, sku, definition, language="pl", inherited=False):
        product = _make_bare_product(channel=channel, sku=sku)
        return GapFindingFactory(
            product=product, definition=definition, channel_idx=channel.idx, language=language, inherited=inherited
        )

    def test_unknown_check_raises(self):
        with pytest.raises(ValueError, match="unknown gap definition key"):
            enrichment_adapter.find_gaps("no-such-rule", {}, {"channel": "c"})

    def test_missing_channel_raises(self):
        self._rule()
        with pytest.raises(ValueError, match="scope.channel is required"):
            enrichment_adapter.find_gaps("desc-rule", {}, {})

    def test_returns_attribute_candidates(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule()
        self._finding(channel=channel, sku="G1", definition=definition, language="pl")

        candidates = enrichment_adapter.find_gaps("desc-rule", {}, {"channel": channel.idx})

        assert candidates == [
            {
                "target_module": "pim",
                "target_type": "product",
                "subject_ref": "G1",
                "priority": "critical",
                "definition_key": "desc-rule",
                "target_kind": "attribute_value",
                "target_locator": {"channel": channel.idx, "language": "pl", "feature_idx": "description"},
            }
        ]

    def test_picture_check_candidate_shape(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule(
            key="pic-rule", check_key=models.GapCheck.PICTURE_PRESENT, severity=models.GapSeverity.WARNING, params={}
        )
        self._finding(channel=channel, sku="G2", definition=definition, language=None)

        candidates = enrichment_adapter.find_gaps("pic-rule", {}, {"channel": channel.idx})

        assert candidates[0]["target_kind"] == "picture"
        assert candidates[0]["target_locator"] == {"channel": channel.idx}
        assert candidates[0]["priority"] == "warning"

    def test_picture_alt_check_candidate_shape(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule(
            key="alt-rule",
            check_key=models.GapCheck.PICTURE_ALT_PRESENT,
            severity=models.GapSeverity.WARNING,
            params={},
        )
        self._finding(channel=channel, sku="G12", definition=definition, language="en")

        candidates = enrichment_adapter.find_gaps("alt-rule", {}, {"channel": channel.idx})

        assert candidates[0]["target_kind"] == "picture_alt"
        assert candidates[0]["target_locator"] == {"channel": channel.idx, "language": "en"}
        assert candidates[0]["priority"] == "warning"

    def test_feature_set_check_candidate_shape(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule(key="fs-rule", check_key=models.GapCheck.FEATURE_SET_DEFAULT, params={})
        self._finding(channel=channel, sku="G11", definition=definition, language=None)

        candidates = enrichment_adapter.find_gaps("fs-rule", {}, {"channel": channel.idx})

        assert candidates[0]["target_kind"] == "feature_set"
        assert candidates[0]["target_locator"] == {"channel": channel.idx}
        assert candidates[0]["definition_key"] == "fs-rule"

    def test_category_check_candidate_shape(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule(key="cat-rule", check_key=models.GapCheck.CATEGORY_PRESENT, params={})
        self._finding(channel=channel, sku="G14", definition=definition, language=None)

        candidates = enrichment_adapter.find_gaps("cat-rule", {}, {"channel": channel.idx})

        assert candidates[0]["target_kind"] == "category"  # NOT the attribute_value fallback
        assert candidates[0]["target_locator"] == {"channel": channel.idx}

    def test_feature_set_findings_survive_language_filter(self):
        # Structural findings are language-neutral (language=NULL) — a language-scoped pull
        # must keep them via the Q(language__isnull=True) branch.
        channel = ChannelFactory(is_default=True)
        definition = self._rule(key="fs-lang", check_key=models.GapCheck.FEATURE_SET_DEFAULT, params={})
        self._finding(channel=channel, sku="G12", definition=definition, language=None)
        self._finding(channel=channel, sku="G13", definition=definition, language=None)

        candidates = enrichment_adapter.find_gaps("fs-lang", {}, {"channel": channel.idx, "language": "en"})

        assert sorted(c["subject_ref"] for c in candidates) == ["G12", "G13"]

    def test_other_channel_excluded(self):
        channel = ChannelFactory(is_default=True)
        other = ChannelFactory()
        definition = self._rule()
        self._finding(channel=channel, sku="G3", definition=definition)
        self._finding(channel=other, sku="G4", definition=definition)

        candidates = enrichment_adapter.find_gaps("desc-rule", {}, {"channel": channel.idx})

        assert [c["subject_ref"] for c in candidates] == ["G3"]

    def test_inherited_excluded(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule()
        self._finding(channel=channel, sku="G5", definition=definition, inherited=True)
        self._finding(channel=channel, sku="G6", definition=definition)

        candidates = enrichment_adapter.find_gaps("desc-rule", {}, {"channel": channel.idx})

        assert [c["subject_ref"] for c in candidates] == ["G6"]

    def test_language_filter_keeps_neutral(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule()
        self._finding(channel=channel, sku="G7", definition=definition, language="pl")
        self._finding(channel=channel, sku="G8", definition=definition, language="en")
        self._finding(channel=channel, sku="G9", definition=definition, language=None)

        candidates = enrichment_adapter.find_gaps("desc-rule", {}, {"channel": channel.idx, "language": "en"})

        assert sorted(c["subject_ref"] for c in candidates) == ["G8", "G9"]

    def test_paging_is_stable_by_product_pk(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule()
        for n in range(150):
            self._finding(channel=channel, sku=f"P{n:03d}", definition=definition)

        scope = {"channel": channel.idx}
        page1 = enrichment_adapter.find_gaps("desc-rule", {}, {**scope, "page": 1})
        page2 = enrichment_adapter.find_gaps("desc-rule", {}, {**scope, "page": 2})
        page3 = enrichment_adapter.find_gaps("desc-rule", {}, {**scope, "page": 3})

        assert len(page1) == 100
        assert len(page2) == 50
        assert page3 == []
        # Disjoint, ordered by product pk — the front of the queue is deterministic.
        assert {c["subject_ref"] for c in page1}.isdisjoint({c["subject_ref"] for c in page2})

    def test_deep_mute_removes_candidate(self):
        channel = ChannelFactory(is_default=True)
        definition = self._rule(key="pic-mute", check_key=models.GapCheck.PICTURE_PRESENT, params={})
        product = _make_bare_product(channel=channel, sku="G10")
        gap_detection_service.detect_for_product(product)
        assert enrichment_adapter.find_gaps("pic-mute", {}, {"channel": channel.idx})

        GapExemptionFactory(product=product, definition=definition, language=None)
        gap_detection_service.detect_for_product(product)

        assert enrichment_adapter.find_gaps("pic-mute", {}, {"channel": channel.idx}) == []


def _make_bare_product(*, channel, sku):
    return ProductFactory(shop=channel, real_product=RealProductFactory(sku=sku), feature_set=FeatureSetFactory())


def _pic_locator(channel):
    return {"channel": channel.idx}


@pytest.mark.django_db
class TestPictureReadCurrent:
    def test_no_main_is_empty(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="PIC-R0")

        snap = enrichment_adapter.read_current(
            subject_ref="PIC-R0", target_kind="picture", target_locator=_pic_locator(channel)
        )

        assert snap == {}

    def test_snapshots_existing_main(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="PIC-R1")
        pic = product_picture_service.upload_picture(_image(color="red"))
        product_picture_service.link_picture_to_product(
            channel.idx, "PIC-R1", pic.pk, picture_role="main", position=0, alt_text_t9n={"en": "old"}
        )

        snap = enrichment_adapter.read_current(
            subject_ref="PIC-R1", target_kind="picture", target_locator=_pic_locator(channel)
        )

        assert snap["sha1"] == pic.sha1
        assert snap["role"] == "main"
        assert snap["alt_t9n"] == {"en": "old"}
        assert snap["url"]


@pytest.mark.django_db
class TestPictureApply:
    def test_replace_main_links_new_and_drops_old(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="PIC-A1")
        old = product_picture_service.upload_picture(_image(color="red"))
        product_picture_service.link_picture_to_product(channel.idx, "PIC-A1", old.pk, picture_role="main", position=0)

        proposal = _Proposal(
            subject_ref="PIC-A1",
            target_locator=_pic_locator(channel),
            target_kind="picture",
            proposed_value={"op": "replace_main", "alt_t9n": {"en": "new alt"}},
            staged_image=_image(color="blue"),
        )

        enrichment_adapter.apply(proposal)

        mains = ProductPicture.objects.filter(product=product, picture_role=PictureRoleEnum.MAIN)
        assert mains.count() == 1
        new_main = mains.first()
        assert new_main.picture_id != old.pk  # main swapped
        assert new_main.alt_text_t9n == {"en": "new alt"}
        assert Picture.objects.filter(pk=old.pk).exists()  # old Picture kept as undo anchor

    def test_replace_main_when_none_exists(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="PIC-A2")
        proposal = _Proposal(
            subject_ref="PIC-A2",
            target_locator=_pic_locator(channel),
            target_kind="picture",
            proposed_value={"op": "replace_main"},
            staged_image=_image(color="green"),
        )

        enrichment_adapter.apply(proposal)

        assert ProductPicture.objects.filter(product=product, picture_role=PictureRoleEnum.MAIN).count() == 1

    def test_unsupported_op_raises(self):
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="PIC-A3")
        proposal = _Proposal(
            subject_ref="PIC-A3",
            target_locator=_pic_locator(channel),
            target_kind="picture",
            proposed_value={"op": "gallery"},
            staged_image=_image(),
        )

        with pytest.raises(ValueError, match="unsupported picture op"):
            enrichment_adapter.apply(proposal)


@pytest.mark.django_db
class TestPictureRevert:
    def test_revert_relinks_old_main_by_sha1(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="PIC-V1")
        old = product_picture_service.upload_picture(_image(color="red"))  # stays in the pool
        new = product_picture_service.upload_picture(_image(color="blue"))
        product_picture_service.link_picture_to_product(channel.idx, "PIC-V1", new.pk, picture_role="main", position=0)

        proposal = _Proposal(
            subject_ref="PIC-V1",
            target_locator=_pic_locator(channel),
            target_kind="picture",
            current_snapshot={"sha1": old.sha1, "role": "main", "position": 0, "alt_t9n": {"en": "old"}},
        )

        enrichment_adapter.revert(proposal)

        main = ProductPicture.objects.get(product=product, picture_role=PictureRoleEnum.MAIN)
        assert main.picture_id == old.pk
        assert main.alt_text_t9n == {"en": "old"}

    def test_revert_empty_snapshot_drops_main(self):
        channel = ChannelFactory(is_default=True)
        product = _make_bare_product(channel=channel, sku="PIC-V2")
        cur = product_picture_service.upload_picture(_image(color="blue"))
        product_picture_service.link_picture_to_product(channel.idx, "PIC-V2", cur.pk, picture_role="main", position=0)

        proposal = _Proposal(
            subject_ref="PIC-V2", target_locator=_pic_locator(channel), target_kind="picture", current_snapshot={}
        )

        enrichment_adapter.revert(proposal)

        assert not ProductPicture.objects.filter(product=product, picture_role=PictureRoleEnum.MAIN).exists()


@pytest.mark.django_db
class TestReleaseUndoAnchor:
    """etap-10 GC: reclaim the displaced/orphaned Picture once undo expires — never a shared SHA1."""

    def test_gc_deletes_unreferenced_displaced_picture(self):
        # An applied proposal's old main sits unlinked in the pool (0 refs) — GC reclaims it + the file.
        old = product_picture_service.upload_picture(_image(color="red"))
        path = old.image.path
        proposal = _Proposal(
            subject_ref="GC-1",
            target_locator={"channel": "eu"},
            target_kind="picture",
            current_snapshot={"sha1": old.sha1},
        )

        reclaimed = enrichment_adapter.release_undo_anchor(proposal)

        assert reclaimed == 1
        assert not Picture.objects.filter(pk=old.pk).exists()
        assert not os.path.isfile(path)  # post_delete signal removed the physical file

    def test_gc_keeps_picture_still_linked_to_another_product(self):
        # Same SHA1 is the live main of a *different* product — deleting it would corrupt that product.
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="GC-OTHER")
        shared = product_picture_service.upload_picture(_image(color="blue"))
        product_picture_service.link_picture_to_product(
            channel.idx, "GC-OTHER", shared.pk, picture_role="main", position=0
        )
        proposal = _Proposal(
            subject_ref="GC-2",
            target_locator={"channel": "eu"},
            target_kind="picture",
            current_snapshot={"sha1": shared.sha1},
        )

        reclaimed = enrichment_adapter.release_undo_anchor(proposal)

        assert reclaimed == 0
        assert Picture.objects.filter(pk=shared.pk).exists()

    def test_gc_keeps_picture_referenced_by_attribute(self):
        # Referenced via AttributePicture, NOT ProductPicture — proves the guard scans every relation.
        shared = product_picture_service.upload_picture(_image(color="green"))
        AttributePicture.objects.create(attribute=AttributeFactory(feature=FeatureFactory()), picture=shared)
        proposal = _Proposal(
            subject_ref="GC-3",
            target_locator={"channel": "eu"},
            target_kind="picture",
            current_snapshot={"sha1": shared.sha1},
        )

        reclaimed = enrichment_adapter.release_undo_anchor(proposal)

        assert reclaimed == 0
        assert Picture.objects.filter(pk=shared.pk).exists()

    def test_gc_reclaims_reverted_orphan_via_applied_snapshot(self):
        # A reverted proposal: the old main is re-linked (live, kept), the new one is now orphaned (reclaimed).
        channel = ChannelFactory(is_default=True)
        _make_bare_product(channel=channel, sku="GC-REV")
        old = product_picture_service.upload_picture(_image(color="red"))
        product_picture_service.link_picture_to_product(channel.idx, "GC-REV", old.pk, picture_role="main", position=0)
        orphan = product_picture_service.upload_picture(_image(color="blue"))  # unlinked after revert
        proposal = _Proposal(
            subject_ref="GC-REV",
            target_locator={"channel": "eu"},
            target_kind="picture",
            current_snapshot={"sha1": old.sha1},
            applied_snapshot={"sha1": orphan.sha1},
        )

        reclaimed = enrichment_adapter.release_undo_anchor(proposal)

        assert reclaimed == 1
        assert Picture.objects.filter(pk=old.pk).exists()  # re-linked live main kept
        assert not Picture.objects.filter(pk=orphan.pk).exists()  # orphaned new main reclaimed

    def test_noop_for_text_proposal(self):
        before = Picture.objects.count()
        proposal = _Proposal(
            subject_ref="GC-TXT",
            target_locator=_locator(ChannelFactory(is_default=True)),
            target_kind="attribute_value",
            current_snapshot={"text": "anything"},
        )

        assert enrichment_adapter.release_undo_anchor(proposal) == 0
        assert Picture.objects.count() == before

    def test_noop_on_empty_snapshots(self):
        proposal = _Proposal(subject_ref="GC-EMPTY", target_locator={"channel": "eu"}, target_kind="picture")

        assert enrichment_adapter.release_undo_anchor(proposal) == 0


# --- picture_alt (etap-05-extra) ----------------------------------------------


def _alt_channel():
    # Explicit EN default so the channel matches the "en" the locators request — the adapter
    # uses `language` purely as a dict key today, but keep test data internally consistent.
    return ChannelFactory(is_default=True, default_language=LanguageFactory(iso2="EN"))


def _alt_locator(channel, language="en"):
    return {"channel": channel.idx, "language": language}


def _alt_proposal(channel, *, sku, language="en", proposed_value=None, current_snapshot=None):
    return _Proposal(
        subject_ref=sku,
        target_locator=_alt_locator(channel, language),
        target_kind="picture_alt",
        proposed_value=proposed_value,
        current_snapshot=current_snapshot,
    )


def _link_alt_picture(channel, sku, *, color, alt_t9n=None, role="general", position=0):
    pic = product_picture_service.upload_picture(_image(color=color))
    return product_picture_service.link_picture_to_product(
        channel.idx, sku, pic.pk, picture_role=role, position=position, alt_text_t9n=alt_t9n or {}
    )


@pytest.mark.django_db
class TestPictureAltReadCurrent:
    def test_snapshots_all_pictures_with_string_keys(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-R1")
        pp_main = _link_alt_picture(channel, "ALT-R1", color="red", role="main", alt_t9n={"en": "Red front"})
        pp_plain = _link_alt_picture(channel, "ALT-R1", color="blue", position=1)  # no alt yet

        snap = enrichment_adapter.read_current(
            subject_ref="ALT-R1", target_kind="picture_alt", target_locator=_alt_locator(channel, "en")
        )

        assert snap == {"alts": {str(pp_main.pk): "Red front", str(pp_plain.pk): ""}}

    def test_missing_language_is_empty_strings(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-R2")
        pp = _link_alt_picture(channel, "ALT-R2", color="red", alt_t9n={"en": "only-en"})

        snap = enrichment_adapter.read_current(
            subject_ref="ALT-R2", target_kind="picture_alt", target_locator=_alt_locator(channel, "pl")
        )

        assert snap == {"alts": {str(pp.pk): ""}}

    def test_missing_product_is_empty_map(self):
        channel = _alt_channel()

        snap = enrichment_adapter.read_current(
            subject_ref="ALT-GHOST", target_kind="picture_alt", target_locator=_alt_locator(channel, "en")
        )

        assert snap == {"alts": {}}


@pytest.mark.django_db
class TestPictureAltApply:
    def test_apply_merges_language_and_skips_unlisted_pictures(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-A1")
        target = _link_alt_picture(channel, "ALT-A1", color="red", alt_t9n={"pl": "Czerwony"})
        untouched = _link_alt_picture(channel, "ALT-A1", color="blue", position=1, alt_t9n={"pl": "Niebieski"})

        enrichment_adapter.apply(
            _alt_proposal(channel, sku="ALT-A1", language="en", proposed_value={"alts": {str(target.pk): "Red"}})
        )

        target.refresh_from_db()
        untouched.refresh_from_db()
        assert target.alt_text_t9n == {"pl": "Czerwony", "en": "Red"}  # sibling language survived
        assert untouched.alt_text_t9n == {"pl": "Niebieski"}  # picture absent from the map untouched

    def test_apply_unknown_pk_raises_with_no_partial_write(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-A2")
        valid = _link_alt_picture(channel, "ALT-A2", color="red")

        with pytest.raises(ValueError, match="unknown picture_pk"):
            enrichment_adapter.apply(
                _alt_proposal(channel, sku="ALT-A2", proposed_value={"alts": {str(valid.pk): "Red", "999999": "Ghost"}})
            )

        valid.refresh_from_db()
        assert valid.alt_text_t9n == {}  # all-or-nothing: the valid pk was NOT written

    def test_apply_foreign_picture_pk_raises(self):
        # A pk that exists but belongs to ANOTHER product must be rejected like an unknown one.
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-A3")
        _make_bare_product(channel=channel, sku="ALT-OTHER")
        foreign = _link_alt_picture(channel, "ALT-OTHER", color="green")

        with pytest.raises(ValueError, match="unknown picture_pk"):
            enrichment_adapter.apply(
                _alt_proposal(channel, sku="ALT-A3", proposed_value={"alts": {str(foreign.pk): "Hijack"}})
            )

    def test_apply_non_string_alt_raises(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-A4")
        pp = _link_alt_picture(channel, "ALT-A4", color="red")

        with pytest.raises(ValueError, match="expects a string alt"):
            enrichment_adapter.apply(
                _alt_proposal(channel, sku="ALT-A4", proposed_value={"alts": {str(pp.pk): {"en": "nested"}}})
            )

    def test_apply_non_numeric_pk_raises(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-A5")

        with pytest.raises(ValueError, match="invalid picture_pk"):
            enrichment_adapter.apply(_alt_proposal(channel, sku="ALT-A5", proposed_value={"alts": {"not-a-pk": "x"}}))

    def test_apply_empty_alts_raises(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-A6")

        with pytest.raises(ValueError, match="non-empty 'alts'"):
            enrichment_adapter.apply(_alt_proposal(channel, sku="ALT-A6", proposed_value={"alts": {}}))

    def test_apply_empty_string_alt_raises(self):
        # An applied "" would never clear the finding (the check treats "" as missing) — the
        # enrichment loop would respawn the candidate forever. Only revert may restore "".
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-A8")
        pp = _link_alt_picture(channel, "ALT-A8", color="red")

        with pytest.raises(ValueError, match="restore-only"):
            enrichment_adapter.apply(_alt_proposal(channel, sku="ALT-A8", proposed_value={"alts": {str(pp.pk): "   "}}))

        pp.refresh_from_db()
        assert pp.alt_text_t9n == {}  # nothing written

    def test_apply_enqueues_gap_recompute(self):
        # The write goes through pp.save(), so the ProductPicture post_save gap handler fires
        # and the picture-alt finding gets recomputed away.
        channel = _alt_channel()
        product = _make_bare_product(channel=channel, sku="ALT-A7")
        pp = _link_alt_picture(channel, "ALT-A7", color="red")

        with (
            mock.patch("django_pim.signals.handlers.is_gaps_enabled", return_value=True),
            mock.patch("django_pim.signals.handlers.enqueue_gap_recompute") as enqueue,
        ):
            enrichment_adapter.apply(_alt_proposal(channel, sku="ALT-A7", proposed_value={"alts": {str(pp.pk): "Red"}}))

        pp.refresh_from_db()
        assert pp.alt_text_t9n == {"en": "Red"}  # the write happened — the mock alone can't pass
        enqueue.assert_called_with(product.pk)


@pytest.mark.django_db
class TestPictureAltRevert:
    def test_revert_restores_snapshot_language_only(self):
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-V1")
        pp = _link_alt_picture(channel, "ALT-V1", color="red", alt_t9n={"en": "AI alt", "pl": "Polski"})

        enrichment_adapter.revert(
            _alt_proposal(channel, sku="ALT-V1", language="en", current_snapshot={"alts": {str(pp.pk): "old"}})
        )

        pp.refresh_from_db()
        assert pp.alt_text_t9n == {"en": "old", "pl": "Polski"}  # restore merges, never replaces the dict

    def test_revert_restores_snapshotted_empty_string(self):
        # The snapshot stores "" for pictures that had no alt at intake — revert MUST be able to
        # write that "" back (unlike apply, where empty strings are rejected as restore-only).
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-V3")
        pp = _link_alt_picture(channel, "ALT-V3", color="red", alt_t9n={"en": "AI alt", "pl": "Polski"})

        enrichment_adapter.revert(
            _alt_proposal(channel, sku="ALT-V3", language="en", current_snapshot={"alts": {str(pp.pk): ""}})
        )

        pp.refresh_from_db()
        assert pp.alt_text_t9n == {"en": "", "pl": "Polski"}  # en blanked, sibling untouched

    def test_revert_empty_snapshot_is_noop(self):
        # Unlike feature_set (no empty terminal state → hard error), an empty alts map is a
        # legitimate snapshot: the product had no pictures at intake — nothing to restore.
        channel = _alt_channel()
        _make_bare_product(channel=channel, sku="ALT-V2")

        enrichment_adapter.revert(_alt_proposal(channel, sku="ALT-V2", current_snapshot={"alts": {}}))

    def test_release_undo_anchor_noop_for_picture_alt(self):
        # Alt proposals carry no media binary — the GC hook must never touch them.
        proposal = _alt_proposal(_alt_channel(), sku="ALT-GC", current_snapshot={"alts": {"1": "x"}})

        assert enrichment_adapter.release_undo_anchor(proposal) == 0
