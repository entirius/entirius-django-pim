# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Admin API tests for the quality-gaps highlighter (etap-04).

Covers GapDefinition CRUD, the bulk findings endpoint, the recompute trigger + status, the
soft-compat gap_* fields on the product response, and the 500-no-leak contract.

URL prefix in standalone module tests: /api/pim/admin/ (the service mounts the same routes at
/api/pim/v2/admin/).
"""

from unittest.mock import patch

import pytest

from django_pim.models import Product
from django_pim.models.pim_settings import PimSettings
from tests.factories import GapDefinitionFactory, GapFindingFactory, ProductFactory, ShopFactory

GAPDEFS_URL = "/api/pim/admin/gap-definitions/"


def _detail_url(key: str) -> str:
    return f"/api/pim/admin/gap-definitions/{key}/"


# ============================================================================
# Auth
# ============================================================================


@pytest.mark.django_db
class TestGapDefinitionAuth:
    def test_unauthenticated_returns_401(self, api_client):
        assert api_client.get(GAPDEFS_URL).status_code == 401

    def test_regular_user_returns_403(self, api_client, regular_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        assert api_client.get(GAPDEFS_URL).status_code == 403

    def test_unauthenticated_create_returns_401(self, api_client):
        assert api_client.post(GAPDEFS_URL, {"key": "x"}, format="json").status_code == 401


# ============================================================================
# GapDefinition CRUD
# ============================================================================


@pytest.mark.django_db
class TestGapDefinitionCRUD:
    def test_list_returns_pagination_envelope(self, authenticated_client):
        GapDefinitionFactory()
        response = authenticated_client.get(GAPDEFS_URL)
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"count", "next", "previous", "results"}
        assert body["count"] >= 1

    def test_create_returns_201(self, authenticated_client):
        payload = {
            "key": "pl-description",
            "check_key": "feature_present",
            "params": {"feature_idx": "description"},
            "severity": "critical",
            "label_t9n": {"en": "Missing description"},
            "active": True,
            "display_order": 5,
        }
        response = authenticated_client.post(GAPDEFS_URL, payload, format="json")
        assert response.status_code == 201
        body = response.json()
        assert body["key"] == "pl-description"
        assert body["severity"] == "critical"
        assert body["languages"] is None  # null, not omitted (API contract)

    def test_create_duplicate_key_returns_400(self, authenticated_client):
        GapDefinitionFactory(key="dup-gap")
        payload = {
            "key": "dup-gap",
            "check_key": "feature_present",
            "params": {"feature_idx": "description"},
            "severity": "warning",
        }
        assert authenticated_client.post(GAPDEFS_URL, payload, format="json").status_code == 400

    def test_create_invalid_check_key_returns_400(self, authenticated_client):
        payload = {"key": "bad-check", "check_key": "not_a_check", "params": {}, "severity": "critical"}
        assert authenticated_client.post(GAPDEFS_URL, payload, format="json").status_code == 400

    def test_create_invalid_params_returns_400(self, authenticated_client):
        # feature_present requires feature_idx; bogus key is outside the allowlist.
        payload = {"key": "bad-params", "check_key": "feature_present", "params": {"bogus": 1}, "severity": "critical"}
        assert authenticated_client.post(GAPDEFS_URL, payload, format="json").status_code == 400

    def test_create_invalid_severity_returns_400(self, authenticated_client):
        payload = {
            "key": "bad-sev",
            "check_key": "feature_present",
            "params": {"feature_idx": "description"},
            "severity": "fatal",
        }
        assert authenticated_client.post(GAPDEFS_URL, payload, format="json").status_code == 400

    def test_retrieve_returns_200(self, authenticated_client):
        d = GapDefinitionFactory(key="get-me")
        response = authenticated_client.get(_detail_url(d.key))
        assert response.status_code == 200
        assert response.json()["key"] == "get-me"

    def test_retrieve_missing_returns_404(self, authenticated_client):
        assert authenticated_client.get(_detail_url("nope-xyz")).status_code == 404

    def test_update_severity_returns_200(self, authenticated_client):
        d = GapDefinitionFactory(key="sev-edit", severity="critical")
        response = authenticated_client.patch(_detail_url(d.key), {"severity": "warning"}, format="json")
        assert response.status_code == 200
        assert response.json()["severity"] == "warning"

    def test_update_active_false_returns_200(self, authenticated_client):
        d = GapDefinitionFactory(key="disable-me", active=True)
        response = authenticated_client.patch(_detail_url(d.key), {"active": False}, format="json")
        assert response.status_code == 200
        assert response.json()["active"] is False

    def test_update_service_rejects_non_editable_field(self):
        # The API schema strips unknown fields (first gate); the service whitelist is the defense for
        # direct callers (bridges, commands). Exercised at the service layer.
        from django_pim.services import update_gap_definition

        d = GapDefinitionFactory(key="immutable-key")
        with pytest.raises(ValueError, match="not editable"):
            update_gap_definition(d.key, {"key": "renamed"})

    def test_update_missing_returns_404(self, authenticated_client):
        assert authenticated_client.patch(_detail_url("nope"), {"active": False}, format="json").status_code == 404

    def test_delete_returns_200_then_404(self, authenticated_client):
        d = GapDefinitionFactory(key="del-me")
        assert authenticated_client.delete(_detail_url(d.key)).status_code == 200
        assert authenticated_client.get(_detail_url(d.key)).status_code == 404

    def test_list_invalid_ordering_returns_400(self, authenticated_client):
        assert authenticated_client.get(GAPDEFS_URL, {"ordering": "bogus"}).status_code == 400


# ============================================================================
# Bulk findings
# ============================================================================


@pytest.mark.django_db
class TestGapFindingsBulk:
    def _setup(self):
        channel = ShopFactory()
        product = ProductFactory(shop=channel)
        definition = GapDefinitionFactory(key="f-desc", severity="critical")
        GapFindingFactory(
            product=product, definition=definition, channel_idx=channel.idx, language="pl", severity="critical"
        )
        return channel, product

    def _url(self, channel_idx: str) -> str:
        return f"/api/pim/admin/{channel_idx}/gaps/findings/"

    def test_bulk_findings_grouped_by_product(self, authenticated_client):
        channel, product = self._setup()
        response = authenticated_client.get(self._url(channel.idx), {"product_ids": str(product.pk)})
        assert response.status_code == 200
        results = response.json()["results"]
        assert str(product.pk) in results
        assert results[str(product.pk)][0]["definition_key"] == "f-desc"
        assert results[str(product.pk)][0]["severity"] == "critical"

    def test_severity_filter(self, authenticated_client):
        channel, product = self._setup()
        response = authenticated_client.get(
            self._url(channel.idx), {"product_ids": str(product.pk), "severity": "warning"}
        )
        assert response.status_code == 200
        # No warning-severity findings → product absent (sparse).
        assert str(product.pk) not in response.json()["results"]

    def test_invalid_severity_returns_400(self, authenticated_client):
        channel, product = self._setup()
        response = authenticated_client.get(
            self._url(channel.idx), {"product_ids": str(product.pk), "severity": "fatal"}
        )
        assert response.status_code == 400

    def test_language_filter_keeps_neutral(self, authenticated_client):
        channel = ShopFactory()
        product = ProductFactory(shop=channel)
        definition = GapDefinitionFactory(key="pic", severity="warning")
        # language-neutral finding (e.g. picture): language=None must surface under any language filter.
        GapFindingFactory(
            product=product, definition=definition, channel_idx=channel.idx, language=None, severity="warning"
        )
        response = authenticated_client.get(self._url(channel.idx), {"product_ids": str(product.pk), "language": "en"})
        assert response.status_code == 200
        assert str(product.pk) in response.json()["results"]

    def test_only_source_excludes_inherited(self, authenticated_client):
        channel = ShopFactory()
        product = ProductFactory(shop=channel)
        definition = GapDefinitionFactory(key="inh", severity="critical")
        GapFindingFactory(
            product=product,
            definition=definition,
            channel_idx=channel.idx,
            language="pl",
            severity="critical",
            inherited=True,
        )
        response = authenticated_client.get(
            self._url(channel.idx), {"product_ids": str(product.pk), "only_source": "true"}
        )
        assert response.status_code == 200
        assert str(product.pk) not in response.json()["results"]

    def test_missing_product_ids_returns_400(self, authenticated_client):
        channel = ShopFactory()
        assert authenticated_client.get(self._url(channel.idx)).status_code == 400

    def test_non_integer_product_ids_returns_400(self, authenticated_client):
        channel = ShopFactory()
        assert authenticated_client.get(self._url(channel.idx), {"product_ids": "a,b"}).status_code == 400


# ============================================================================
# Exemptions (deep mute, etap-13)
# ============================================================================


@pytest.mark.django_db
class TestGapExemptionAPI:
    def _setup(self):
        channel = ShopFactory()
        product = ProductFactory(shop=channel)
        # picture_present needs no Feature rows — the cheapest rule for API-level tests.
        definition = GapDefinitionFactory(key="pic-rule", check_key="picture_present", params={})
        return channel, product, definition

    def _url(self, channel_idx: str) -> str:
        return f"/api/pim/admin/{channel_idx}/gaps/exemptions/"

    def test_unauthenticated_returns_401(self, api_client):
        channel = ShopFactory()
        assert api_client.get(self._url(channel.idx), {"sku": "x"}).status_code == 401

    def test_regular_user_returns_403(self, api_client, regular_token):
        channel = ShopFactory()
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        assert api_client.get(self._url(channel.idx), {"sku": "x"}).status_code == 403

    def test_create_returns_201_and_removes_finding(self, authenticated_client):
        channel, product, definition = self._setup()
        GapFindingFactory(
            product=product, definition=definition, channel_idx=channel.idx, language=None, severity="critical"
        )
        payload = {"sku": product.real_product.sku, "definition_key": "pic-rule", "reason": "no picture needed"}

        response = authenticated_client.post(self._url(channel.idx), payload, format="json")

        assert response.status_code == 201
        body = response.json()
        assert body["definition_key"] == "pic-rule"
        assert body["language"] is None
        assert body["reason"] == "no picture needed"
        # The create re-detects immediately — the muted finding is gone.
        from django_pim.models import GapFinding

        assert GapFinding.objects.filter(product=product).count() == 0

    def test_create_duplicate_returns_400(self, authenticated_client):
        channel, product, _ = self._setup()
        payload = {"sku": product.real_product.sku, "definition_key": "pic-rule"}
        assert authenticated_client.post(self._url(channel.idx), payload, format="json").status_code == 201
        assert authenticated_client.post(self._url(channel.idx), payload, format="json").status_code == 400

    def test_create_unknown_definition_returns_404(self, authenticated_client):
        channel, product, _ = self._setup()
        payload = {"sku": product.real_product.sku, "definition_key": "no-such-rule"}
        assert authenticated_client.post(self._url(channel.idx), payload, format="json").status_code == 404

    def test_create_unknown_sku_returns_404(self, authenticated_client):
        channel, _, _ = self._setup()
        payload = {"sku": "no-such-sku", "definition_key": "pic-rule"}
        assert authenticated_client.post(self._url(channel.idx), payload, format="json").status_code == 404

    def test_list_requires_sku(self, authenticated_client):
        channel = ShopFactory()
        assert authenticated_client.get(self._url(channel.idx)).status_code == 400

    def test_list_returns_exemptions(self, authenticated_client):
        channel, product, _ = self._setup()
        payload = {"sku": product.real_product.sku, "definition_key": "pic-rule"}
        authenticated_client.post(self._url(channel.idx), payload, format="json")

        response = authenticated_client.get(self._url(channel.idx), {"sku": product.real_product.sku})

        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["sku"] == product.real_product.sku

    def test_delete_returns_200_then_404(self, authenticated_client):
        channel, product, _ = self._setup()
        payload = {"sku": product.real_product.sku, "definition_key": "pic-rule"}
        created = authenticated_client.post(self._url(channel.idx), payload, format="json").json()
        url = f"{self._url(channel.idx)}{created['id']}/"

        assert authenticated_client.delete(url).status_code == 200
        assert authenticated_client.delete(url).status_code == 404

    def test_delete_cross_channel_returns_404(self, authenticated_client):
        channel, product, _ = self._setup()
        other = ShopFactory()
        payload = {"sku": product.real_product.sku, "definition_key": "pic-rule"}
        created = authenticated_client.post(self._url(channel.idx), payload, format="json").json()

        response = authenticated_client.delete(f"{self._url(other.idx)}{created['id']}/")

        assert response.status_code == 404


# ============================================================================
# Recompute + status
# ============================================================================


@pytest.mark.django_db
class TestGapRecomputeAndStatus:
    RECOMPUTE_URL = "/api/pim/admin/gaps/recompute/"
    STATUS_URL = "/api/pim/admin/gaps/status/"

    @patch("django_pim.api.admin.views.gaps_views.trigger_full_recompute", return_value={"status": "started"})
    def test_recompute_returns_202_started(self, _mock, authenticated_client):
        response = authenticated_client.post(self.RECOMPUTE_URL, {}, format="json")
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "started"
        assert body["running"] is True

    @patch("django_pim.api.admin.views.gaps_views.trigger_full_recompute", return_value={"status": "already_running"})
    def test_recompute_already_running_returns_202(self, _mock, authenticated_client):
        response = authenticated_client.post(self.RECOMPUTE_URL, {}, format="json")
        assert response.status_code == 202
        assert response.json()["status"] == "already_running"

    def test_recompute_requires_admin(self, api_client, regular_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        assert api_client.post(self.RECOMPUTE_URL, {}, format="json").status_code == 403

    def test_status_returns_200_with_fields(self, authenticated_client):
        response = authenticated_client.get(self.STATUS_URL)
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {
            "gaps_enabled",
            "rules_changed_at",
            "recomputed_at",
            "is_stale",
            "recompute_running",
        }

    def test_status_is_stale_when_rules_changed_after_recompute(self, authenticated_client):
        from django.utils import timezone

        PimSettings.load()  # ensure the singleton row exists
        now = timezone.now()
        PimSettings.objects.filter(pk=1).update(
            gaps_recomputed_at=now - timezone.timedelta(hours=1), gaps_rules_changed_at=now
        )
        body = authenticated_client.get(self.STATUS_URL).json()
        assert body["is_stale"] is True


# ============================================================================
# Settings (featureset-cascade etap-04)
# ============================================================================


@pytest.mark.django_db
class TestGapSettings:
    SETTINGS_URL = "/api/pim/admin/gaps/settings/"

    def test_get_returns_model_default(self, authenticated_client):
        response = authenticated_client.get(self.SETTINGS_URL)
        assert response.status_code == 200
        assert response.json() == {"gaps_skip_default_featureset": True}

    def test_patch_persists_value(self, authenticated_client):
        response = authenticated_client.patch(self.SETTINGS_URL, {"gaps_skip_default_featureset": False}, format="json")
        assert response.status_code == 200
        assert response.json() == {"gaps_skip_default_featureset": False}
        assert PimSettings.load().gaps_skip_default_featureset is False

    def test_patch_change_stamps_rules_changed(self, authenticated_client):
        assert PimSettings.load().gaps_rules_changed_at is None
        authenticated_client.patch(self.SETTINGS_URL, {"gaps_skip_default_featureset": False}, format="json")
        assert PimSettings.load().gaps_rules_changed_at is not None

    def test_patch_same_value_does_not_stamp(self, authenticated_client):
        assert PimSettings.load().gaps_skip_default_featureset is True
        authenticated_client.patch(self.SETTINGS_URL, {"gaps_skip_default_featureset": True}, format="json")
        assert PimSettings.load().gaps_rules_changed_at is None

    def test_patch_missing_field_returns_400(self, authenticated_client):
        assert authenticated_client.patch(self.SETTINGS_URL, {}, format="json").status_code == 400

    def test_patch_invalid_value_returns_400(self, authenticated_client):
        response = authenticated_client.patch(
            self.SETTINGS_URL, {"gaps_skip_default_featureset": "banana"}, format="json"
        )
        assert response.status_code == 400

    def test_requires_admin(self, api_client, regular_token):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")
        assert api_client.get(self.SETTINGS_URL).status_code == 403
        assert (
            api_client.patch(self.SETTINGS_URL, {"gaps_skip_default_featureset": False}, format="json").status_code
            == 403
        )

    def test_unauthenticated_returns_401(self, api_client):
        assert api_client.get(self.SETTINGS_URL).status_code == 401

    @patch("django_pim.api.admin.views.gaps_views.get_gaps_settings", side_effect=RuntimeError("secret db detail"))
    def test_internal_error_does_not_leak(self, _mock, authenticated_client):
        response = authenticated_client.get(self.SETTINGS_URL)
        assert response.status_code == 500
        assert "secret db detail" not in str(response.json())

    def test_feature_set_default_flip_stamps_rules_changed(self, authenticated_client):
        from tests.factories import FeatureSetFactory

        fs = FeatureSetFactory(is_default=False)
        assert PimSettings.load().gaps_rules_changed_at is None

        response = authenticated_client.patch(
            f"/api/pim/admin/feature-sets/{fs.idx}/", {"is_default": True}, format="json"
        )

        assert response.status_code == 200
        assert PimSettings.load().gaps_rules_changed_at is not None

    def test_feature_set_update_without_default_change_does_not_stamp(self, authenticated_client):
        from tests.factories import FeatureSetFactory

        fs = FeatureSetFactory(is_default=False)
        response = authenticated_client.patch(
            f"/api/pim/admin/feature-sets/{fs.idx}/", {"name": "Renamed"}, format="json"
        )

        assert response.status_code == 200
        assert PimSettings.load().gaps_rules_changed_at is None


# ============================================================================
# Soft-compat: gap_* on the product response
# ============================================================================


@pytest.mark.django_db
class TestProductSoftCompat:
    def _product_with_gaps(self):
        channel = ShopFactory()
        product = ProductFactory(shop=channel)
        Product.objects.filter(pk=product.pk).update(gap_worst_severity="critical", gap_count=2)
        return channel, product

    def test_list_includes_gap_fields(self, authenticated_client):
        channel, product = self._product_with_gaps()
        response = authenticated_client.get(f"/api/pim/admin/{channel.idx}/products/")
        assert response.status_code == 200
        row = next(r for r in response.json()["results"] if r["pk"] == product.pk)
        assert row["gap_worst_severity"] == "critical"
        assert row["gap_count"] == 2
        assert "gap_evaluated_at" in row

    def test_detail_includes_gap_fields(self, authenticated_client):
        channel, product = self._product_with_gaps()
        response = authenticated_client.get(f"/api/pim/admin/{channel.idx}/products/{product.sku}/")
        assert response.status_code == 200
        body = response.json()
        assert body["gap_worst_severity"] == "critical"
        assert body["gap_count"] == 2

    def test_sort_by_gap_severity_returns_200(self, authenticated_client):
        channel, _ = self._product_with_gaps()
        response = authenticated_client.get(
            f"/api/pim/admin/{channel.idx}/products/", {"ordering": "gap_worst_severity"}
        )
        assert response.status_code == 200

    def test_sort_unknown_falls_back_to_200(self, authenticated_client):
        # Product-list ordering keeps the established silent-fallback contract (only mapped values
        # reach order_by — secure). Strict sort→400 is enforced on the new GapDefinition list instead.
        channel = ShopFactory()
        response = authenticated_client.get(f"/api/pim/admin/{channel.idx}/products/", {"ordering": "bogus_field"})
        assert response.status_code == 200

    def test_filter_gap_severity_returns_200(self, authenticated_client):
        channel, _ = self._product_with_gaps()
        response = authenticated_client.get(f"/api/pim/admin/{channel.idx}/products/", {"gap_severity": "critical"})
        assert response.status_code == 200

    def test_filter_gap_severity_invalid_returns_400(self, authenticated_client):
        channel = ShopFactory()
        response = authenticated_client.get(f"/api/pim/admin/{channel.idx}/products/", {"gap_severity": "fatal"})
        assert response.status_code == 400


# ============================================================================
# 500 must not leak internals
# ============================================================================


@pytest.mark.django_db
class TestInternalErrorNoLeak:
    @patch(
        "django_pim.api.admin.views.gaps_views.list_gap_definitions",
        side_effect=RuntimeError("secret db dsn postgres://user:pw@host/db"),
    )
    def test_unexpected_error_returns_sanitized_500(self, _mock, authenticated_client):
        response = authenticated_client.get(GAPDEFS_URL)
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert "secret" not in detail
        assert "postgres" not in detail
        assert "Internal server error" in detail
