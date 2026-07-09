# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Model tests for the pim-quality-score gap highlighter (etap-01).

Covers GapDefinition/GapFinding constraints + defaults, the 3 Product rollup
columns, FK CASCADE cleanup, and the silent `.update()` rollup write path.
"""

import os

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from django_pim.models import GapCheck, GapDefinition, GapExemption, GapFinding, GapSeverity, Product

from .factories import (
    ChannelFactory,
    FeatureFactory,
    GapDefinitionFactory,
    GapExemptionFactory,
    GapFindingFactory,
    ProductFactory,
    RealProductFactory,
)


@pytest.mark.django_db
class TestGapDefinition:
    def test_create_with_defaults(self):
        # Arrange / Act
        definition = GapDefinition.objects.create(
            key="pl-description", check_key=GapCheck.FEATURE_PRESENT, severity=GapSeverity.CRITICAL
        )

        # Assert
        assert definition.active is True
        assert definition.display_order == 0
        assert definition.params == {}
        assert definition.label_t9n == {}
        assert definition.languages is None
        assert definition.channels is None
        assert definition.created_at is not None
        assert definition.modified_at is not None

    def test_key_is_unique(self):
        # Arrange — bypass factory get_or_create to hit the DB constraint directly
        GapDefinition.objects.create(key="dup-key", check_key=GapCheck.FEATURE_PRESENT, severity=GapSeverity.CRITICAL)

        # Act / Assert
        with pytest.raises(IntegrityError):
            GapDefinition.objects.create(
                key="dup-key", check_key=GapCheck.FEATURE_PRESENT, severity=GapSeverity.CRITICAL
            )

    def test_severity_choices(self):
        # Arrange / Act / Assert
        assert {c[0] for c in GapSeverity.choices} == {"critical", "warning"}

    def test_check_choices(self):
        # Arrange / Act / Assert
        assert {c[0] for c in GapCheck.choices} == {
            "feature_present",
            "feature_min_length",
            "picture_present",
            "picture_min_count",
            "picture_alt_present",
            "category_present",
            "feature_set_default",
        }

    def test_str(self):
        # Arrange
        definition = GapDefinitionFactory(key="pl-description")

        # Act / Assert
        assert str(definition) == "GapDefinition(key=pl-description)"

    def test_json_defaults_are_isolated(self):
        # Arrange — exercise the model default=dict (no params passed), guard against
        # a refactor to `default={}` that would alias the dict across instances
        d1 = GapDefinition.objects.create(key="d1", check_key=GapCheck.FEATURE_PRESENT, severity=GapSeverity.CRITICAL)
        d2 = GapDefinition.objects.create(key="d2", check_key=GapCheck.FEATURE_PRESENT, severity=GapSeverity.CRITICAL)

        # Act
        d1.params["x"] = 1

        # Assert — mutating one must not bleed into the other
        assert d2.params == {}


@pytest.mark.django_db
class TestGapFinding:
    def test_create_with_fks(self):
        # Arrange
        product = ProductFactory()
        definition = GapDefinitionFactory()

        # Act
        finding = GapFinding.objects.create(
            product=product,
            definition=definition,
            channel_idx=product.shop.idx,
            severity=definition.severity,
            language="pl",
        )

        # Assert
        assert finding.inherited is False
        assert finding.source_channel is None
        assert finding.created_at is not None

    def test_unique_together_product_definition_language(self):
        # Arrange
        finding = GapFindingFactory(language="pl")

        # Act / Assert — same (product, definition, language) collides
        with pytest.raises(IntegrityError):
            GapFinding.objects.create(
                product=finding.product,
                definition=finding.definition,
                channel_idx=finding.channel_idx,
                severity=finding.severity,
                language="pl",
            )

    def test_null_language_findings_coexist(self):
        # Arrange — the etap-02 replace strategy relies on Postgres treating NULL as
        # distinct: two (product, definition, NULL) rows must NOT collide.
        product = ProductFactory()
        definition = GapDefinitionFactory()
        common = {
            "product": product,
            "definition": definition,
            "channel_idx": product.shop.idx,
            "severity": definition.severity,
            "language": None,
        }

        # Act
        GapFinding.objects.create(**common)
        GapFinding.objects.create(**common)

        # Assert
        assert GapFinding.objects.filter(product=product, definition=definition, language=None).count() == 2

    def test_delete_definition_cascades_to_findings(self):
        # Arrange
        finding = GapFindingFactory()
        definition = finding.definition
        assert GapFinding.objects.count() == 1

        # Act
        definition.delete()

        # Assert
        assert GapFinding.objects.count() == 0

    def test_delete_product_cascades_to_findings(self):
        # Arrange
        finding = GapFindingFactory()
        product = finding.product
        assert GapFinding.objects.count() == 1

        # Act
        product.delete()

        # Assert
        assert GapFinding.objects.count() == 0

    def test_str(self):
        # Arrange
        finding = GapFindingFactory()

        # Act / Assert
        assert str(finding) == f"GapFinding(product={finding.product_id}, def={finding.definition_id})"


@pytest.mark.django_db
class TestGapExemption:
    def test_create_with_defaults(self):
        # Arrange / Act
        exemption = GapExemptionFactory()

        # Assert
        assert exemption.language is None
        assert exemption.reason == ""
        assert exemption.created_by is None
        assert exemption.created_at is not None

    def test_unique_constraint_with_language(self):
        # Arrange
        exemption = GapExemptionFactory(language="pl")

        # Act / Assert
        with pytest.raises(IntegrityError):
            GapExemption.objects.create(product=exemption.product, definition=exemption.definition, language="pl")

    def test_two_null_language_rows_collide(self):
        # Arrange — unlike GapFinding, these rows are operator-created, so the constraint
        # uses nulls_distinct=False: two (product, definition, NULL) rows MUST collide.
        exemption = GapExemptionFactory(language=None)

        # Act / Assert
        with pytest.raises(IntegrityError):
            GapExemption.objects.create(product=exemption.product, definition=exemption.definition, language=None)

    def test_delete_definition_cascades(self):
        # Arrange
        exemption = GapExemptionFactory()

        # Act
        exemption.definition.delete()

        # Assert
        assert GapExemption.objects.count() == 0

    def test_delete_product_cascades(self):
        # Arrange
        exemption = GapExemptionFactory()

        # Act
        exemption.product.delete()

        # Assert
        assert GapExemption.objects.count() == 0

    def test_str(self):
        # Arrange
        exemption = GapExemptionFactory(language="en")

        # Act / Assert
        assert str(exemption) == f"GapExemption(product={exemption.product_id}, def={exemption.definition_id}, lang=en)"


@pytest.mark.django_db
class TestProductRollup:
    def test_rollup_defaults(self):
        # Arrange / Act
        product = ProductFactory()

        # Assert
        assert product.gap_worst_severity is None
        assert product.gap_count == 0
        assert product.gap_evaluated_at is None

    def test_silent_update_writes_rollup_without_save(self):
        # Arrange — a finding exists; we update the rollup via the silent path
        finding = GapFindingFactory()
        product = finding.product
        evaluated = timezone.now()

        # Act — MUST use .update(), never instance.save() (PIM signal loop)
        Product.objects.filter(pk=product.pk).update(
            gap_count=1, gap_worst_severity=GapSeverity.CRITICAL.value, gap_evaluated_at=evaluated
        )

        # Assert — all three rollup fields land, read back fresh from DB
        product.refresh_from_db()
        assert product.gap_count == 1
        assert product.gap_worst_severity == GapSeverity.CRITICAL.value
        assert product.gap_evaluated_at == evaluated


_SEED_FIXTURE = os.environ.get("PIM_SEED_FIXTURE", "")


@pytest.mark.django_db
@pytest.mark.skipif(
    not _SEED_FIXTURE or not os.path.exists(_SEED_FIXTURE), reason="set PIM_SEED_FIXTURE to a gaps baseline yaml"
)
def test_seed_fixture_idempotent():
    """Loading the same baseline twice yields no duplicates (explicit pk + unique key)."""
    from django.core.management import call_command

    # Act
    with transaction.atomic():
        call_command("loaddata", "--format=yaml", _SEED_FIXTURE, verbosity=0)
    first = GapDefinition.objects.count()
    with transaction.atomic():
        call_command("loaddata", "--format=yaml", _SEED_FIXTURE, verbosity=0)
    second = GapDefinition.objects.count()

    # Assert — idempotency, not a magic count: the client's rule set grows over time
    # (explicit pk + unique key make the second load a no-op), so assert stability, not "== N".
    assert first >= 1
    assert second == first


@pytest.mark.django_db
class TestDescGrounding:
    """`desc` AI-grounding metadata on the 5 taxonomy entities (featureset-cascade etap-01)."""

    def test_desc_defaults_to_empty_string(self):
        from tests.factories import (
            AttributeFactory,
            AttributesGroupFactory,
            FeatureFactory,
            ProductCategoryFactory,
            ProductLinkTypeFactory,
        )

        # Arrange / Act — one instance per entity, no desc provided
        instances = [
            FeatureFactory(),
            ProductCategoryFactory(),
            AttributesGroupFactory(),
            AttributeFactory(feature=FeatureFactory()),
            ProductLinkTypeFactory(),
        ]

        # Assert — blank, not null (consistent with FeatureSet.desc)
        for instance in instances:
            instance.refresh_from_db()
            assert instance.desc == ""

    def test_desc_persists(self):
        from tests.factories import FeatureFactory

        # Arrange
        feature = FeatureFactory()

        # Act
        feature.desc = "Dominant case colour; plain colours only."
        feature.save()

        # Assert
        feature.refresh_from_db()
        assert feature.desc == "Dominant case colour; plain colours only."


@pytest.mark.django_db
def test_pim_settings_skip_default_featureset_defaults_true():
    from django_pim.models import PimSettings

    # Arrange / Act
    settings = PimSettings.load()

    # Assert — cascade muting is on by default
    assert settings.gaps_skip_default_featureset is True


@pytest.mark.django_db
class TestProductAttributeNullConstraint:
    """pim-fix-1: duplicate (product, feature, NULL attribute) must be rejected by the DB.

    The old unique_together let duplicate rows slip past for attribute=NULL (Postgres treats
    NULL != NULL), crashing the product list via name_lang().get(). Migration 0060 swaps to a
    UniqueConstraint(nulls_distinct=False).
    """

    def test_duplicate_null_attribute_rejected(self):
        from django_pim.models import ProductAttribute

        channel = ChannelFactory()
        product = ProductFactory(real_product=RealProductFactory(sku="DUP-001"), shop=channel)
        feature = FeatureFactory()  # any feature; the constraint is on (product, feature, NULL attribute)

        # bulk_create bypasses model.save()/validate_values — we test the DB constraint,
        # not model validation. nulls_distinct=False must reject the second NULL-attribute row.
        ProductAttribute.objects.bulk_create([ProductAttribute(product=product, feature=feature, attribute=None)])
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductAttribute.objects.bulk_create(
                    [ProductAttribute(product=product, feature=feature, attribute=None)]
                )
