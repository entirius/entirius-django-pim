# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Admin API: per-set required override, required-features endpoint, create error shapes."""

import pytest

from django_pim.models import FeatureInFeatureSet, FeatureScopeEnum, FeatureTypeEnum, Product

from .factories import (
    AttributeFactory,
    ChannelFactory,
    FeatureFactory,
    FeatureInFeatureSetFactory,
    FeatureSetFactory,
)

BASE = "/api/pim/admin"


@pytest.fixture
def setup(db):
    channel = ChannelFactory(idx="shop")
    fs = FeatureSetFactory(idx="battery")
    voltage = FeatureFactory(idx="voltage", feature_type=FeatureTypeEnum.DECIMAL, is_required=True)
    colour = FeatureFactory(idx="colour", feature_type=FeatureTypeEnum.SELECT)
    FeatureInFeatureSetFactory(feature_set=fs, feature=voltage)
    FeatureInFeatureSetFactory(feature_set=fs, feature=colour)
    return fs


def _row(client, url, feature_idx):
    return next(r for r in client.get(url).json()["results"] if r["feature"]["idx"] == feature_idx)


class TestFeaturesInSetExposure:
    def test_effective_and_raw_flags(self, authenticated_client, setup):
        FeatureInFeatureSet.objects.filter(feature__idx="colour").update(is_required=True)
        url = f"{BASE}/feature-sets/battery/features/"

        voltage, colour = _row(authenticated_client, url, "voltage"), _row(authenticated_client, url, "colour")

        assert (voltage["is_required"], voltage["is_required_override"]) == (True, None)
        assert (colour["is_required"], colour["is_required_override"]) == (True, True)

    def test_override_false_un_requires_in_response(self, authenticated_client, setup):
        FeatureInFeatureSet.objects.filter(feature__idx="voltage").update(is_required=False)

        row = _row(authenticated_client, f"{BASE}/feature-sets/battery/features/", "voltage")

        assert (row["is_required"], row["is_required_override"]) == (False, False)

    def test_channel_scoped_list_has_the_fields(self, authenticated_client, setup):
        row = _row(authenticated_client, f"{BASE}/shop/feature-sets/battery/features/", "voltage")

        assert row["is_required"] is True
        assert "is_required_override" in row


class TestBulkAddIsRequired:
    def test_entry_accepts_is_required(self, authenticated_client, setup):
        FeatureFactory(idx="cells", feature_type=FeatureTypeEnum.DECIMAL)
        FeatureFactory(idx="weight", feature_type=FeatureTypeEnum.DECIMAL, is_required=True)

        response = authenticated_client.post(
            f"{BASE}/feature-sets/battery/features/",
            {
                "features": [
                    {"feature_idx": "cells", "is_required": True},
                    {"feature_idx": "weight", "is_required": False},
                ]
            },
            format="json",
        )

        assert response.status_code == 201
        by_idx = {r["feature"]["idx"]: r for r in response.json()}
        assert (by_idx["cells"]["is_required"], by_idx["cells"]["is_required_override"]) == (True, True)
        assert (by_idx["weight"]["is_required"], by_idx["weight"]["is_required_override"]) == (False, False)

    def test_entry_without_key_inherits(self, authenticated_client, setup):
        FeatureFactory(idx="weight", feature_type=FeatureTypeEnum.DECIMAL, is_required=True)

        response = authenticated_client.post(
            f"{BASE}/feature-sets/battery/features/", {"features": [{"feature_idx": "weight"}]}, format="json"
        )

        assert response.json()[0]["is_required_override"] is None
        assert response.json()[0]["is_required"] is True

    def test_override_on_system_feature_is_400(self, authenticated_client, setup):
        FeatureFactory(idx="name", feature_type=FeatureTypeEnum.VARCHAR255_T9N, scope=FeatureScopeEnum.SYSTEM)

        response = authenticated_client.post(
            f"{BASE}/feature-sets/battery/features/",
            {"features": [{"feature_idx": "name", "is_required": True}]},
            format="json",
        )

        assert response.status_code == 400


class TestPatchOverride:
    url = f"{BASE}/feature-sets/battery/features/colour/"

    @pytest.mark.parametrize("value", [True, False, None])
    def test_sets_and_clears(self, authenticated_client, setup, value):
        response = authenticated_client.patch(self.url, {"is_required": value}, format="json")

        assert response.status_code == 200
        assert response.json()["is_required_override"] is value
        assert response.json()["feature"]["idx"] == "colour"
        assert FeatureInFeatureSet.objects.get(feature__idx="colour").is_required is value

    def test_effective_flag_in_response(self, authenticated_client, setup):
        response = authenticated_client.patch(
            f"{BASE}/feature-sets/battery/features/voltage/", {"is_required": False}, format="json"
        )

        assert (response.json()["is_required"], response.json()["is_required_override"]) == (False, False)

    def test_key_is_required(self, authenticated_client, setup):
        response = authenticated_client.patch(self.url, {}, format="json")

        assert response.status_code == 400

    def test_non_boolean_is_400(self, authenticated_client, setup):
        assert authenticated_client.patch(self.url, {"is_required": "maybe"}, format="json").status_code == 400

    def test_system_feature_is_400(self, authenticated_client, setup):
        system = FeatureFactory(idx="name", feature_type=FeatureTypeEnum.VARCHAR255_T9N, scope=FeatureScopeEnum.SYSTEM)
        FeatureInFeatureSetFactory(feature_set=setup, feature=system)

        response = authenticated_client.patch(
            f"{BASE}/feature-sets/battery/features/name/", {"is_required": True}, format="json"
        )

        assert response.status_code == 400
        assert "system" in response.json()["detail"]

    @pytest.mark.parametrize(
        "url",
        [
            f"{BASE}/feature-sets/nope/features/colour/",
            f"{BASE}/feature-sets/battery/features/nope/",
            f"{BASE}/feature-sets/battery/features/orphan/",
        ],
    )
    def test_unknown_references_are_404(self, authenticated_client, setup, url):
        FeatureFactory(idx="orphan")

        assert authenticated_client.patch(url, {"is_required": True}, format="json").status_code == 404

    def test_requires_admin(self, api_client, regular_token, setup):
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {regular_token}")

        assert api_client.patch(self.url, {"is_required": True}, format="json").status_code in (401, 403)

    def test_anonymous_is_rejected(self, api_client, setup):
        assert api_client.patch(self.url, {"is_required": True}, format="json").status_code in (401, 403)

    def test_reorder_keeps_override(self, authenticated_client, setup):
        authenticated_client.patch(self.url, {"is_required": True}, format="json")

        response = authenticated_client.patch(
            f"{BASE}/feature-sets/battery/features/reorder/",
            {"features": [{"feature_idx": "colour", "position": 900}]},
            format="json",
        )

        assert response.status_code == 200
        row = FeatureInFeatureSet.objects.get(feature__idx="colour")
        assert (row.position, row.is_required) == (900, True)


class TestRequiredFeaturesEndpoint:
    def test_lists_feature_with_source(self, authenticated_client, setup):
        FeatureFactory(
            idx="name", feature_type=FeatureTypeEnum.VARCHAR255_T9N, is_required=True, scope=FeatureScopeEnum.SYSTEM
        )
        FeatureInFeatureSet.objects.filter(feature__idx="colour").update(is_required=True)

        response = authenticated_client.get(f"{BASE}/feature-sets/battery/required-features/")

        assert response.status_code == 200
        assert [(r["feature"]["idx"], r["source"]) for r in response.json()] == [
            ("name", "system"),
            ("voltage", "feature"),
            ("colour", "feature_set"),
        ]
        assert response.json()[1]["feature"]["is_required"] is True

    def test_empty_list(self, authenticated_client, db):
        FeatureSetFactory(idx="cable")

        assert authenticated_client.get(f"{BASE}/feature-sets/cable/required-features/").json() == []

    def test_channel_scoped_variant(self, authenticated_client, setup):
        response = authenticated_client.get(f"{BASE}/shop/feature-sets/battery/required-features/")

        assert [r["feature"]["idx"] for r in response.json()] == ["voltage"]

    def test_unknown_set_and_channel_are_404(self, authenticated_client, setup):
        assert authenticated_client.get(f"{BASE}/feature-sets/nope/required-features/").status_code == 404
        assert authenticated_client.get(f"{BASE}/nochan/feature-sets/battery/required-features/").status_code == 404

    def test_anonymous_is_rejected(self, api_client, setup):
        assert api_client.get(f"{BASE}/feature-sets/battery/required-features/").status_code in (401, 403)


class TestProductCreateErrors:
    url = f"{BASE}/shop/products/"

    def _post(self, client, **body):
        return client.post(self.url, {"sku": "SKU-1", "feature_set_idx": "battery", **body}, format="json")

    def test_default_creates_without_required_values(self, authenticated_client, setup):
        assert self._post(authenticated_client).status_code == 201

    def test_setting_on_returns_v2_400_shape(self, authenticated_client, setup, settings):
        settings.PIM_ENFORCE_REQUIRED_ON_CREATE = True

        response = self._post(authenticated_client)

        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["message"]
        assert body["debug_id"]
        assert body["details"] == [
            {
                "field": "attributes.voltage",
                "location": "body",
                "issue": "REQUIRED_FEATURE_MISSING",
                "description": body["details"][0]["description"],
            }
        ]
        assert "voltage" in body["details"][0]["description"]
        assert Product.objects.count() == 0

    def test_one_detail_per_missing_feature_sorted(self, authenticated_client, setup, settings):
        settings.PIM_ENFORCE_REQUIRED_ON_CREATE = True
        FeatureInFeatureSet.objects.filter(feature__idx="colour").update(is_required=True)

        details = self._post(authenticated_client).json()["details"]

        assert [d["field"] for d in details] == ["attributes.colour", "attributes.voltage"]

    def test_supplied_value_creates(self, authenticated_client, setup, settings):
        settings.PIM_ENFORCE_REQUIRED_ON_CREATE = True

        response = self._post(authenticated_client, attributes=[{"feature_idx": "voltage", "value_decimal": "48"}])

        assert response.status_code == 201

    def test_strict_returns_unresolved_400(self, authenticated_client, setup, settings):
        settings.PIM_STRICT_CREATE = True
        AttributeFactory(idx="red", feature=FeatureFactory(idx="other", feature_type=FeatureTypeEnum.SELECT))

        response = self._post(
            authenticated_client,
            attributes=[{"feature_idx": "ghost", "value_txt": "x"}, {"feature_idx": "colour", "attribute_idx": "red"}],
            category_idxs=["nope"],
        )

        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "VALIDATION_ERROR"
        issues = {(d["field"], d["issue"]) for d in body["details"]}
        assert ("attributes.ghost", "UNRESOLVED_ATTRIBUTE") in issues
        assert ("attributes.colour", "UNRESOLVED_ATTRIBUTE") in issues
        assert ("category_idxs.nope", "UNRESOLVED_CATEGORY") in issues
        assert Product.objects.count() == 0

    def test_unknown_channel_is_400_not_500(self, authenticated_client, setup):
        response = authenticated_client.post(
            f"{BASE}/nochan/products/", {"sku": "X", "feature_set_idx": "battery"}, format="json"
        )

        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["details"][0]["field"] == "channel_idx"
        assert body["details"][0]["location"] == "path"

    def test_unknown_feature_set_is_400_not_500(self, authenticated_client, setup):
        response = self._post(authenticated_client, feature_set_idx="nope")

        assert response.status_code == 400
        assert response.json()["details"][0]["field"] == "feature_set_idx"

    def test_duplicate_sku_stays_400_detail(self, authenticated_client, setup, settings):
        self._post(authenticated_client)
        settings.PIM_ENFORCE_REQUIRED_ON_CREATE = True

        response = self._post(authenticated_client)

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


class TestOpenApiContract:
    @pytest.fixture(scope="class")
    def schema(self):
        from drf_spectacular.generators import SchemaGenerator

        return SchemaGenerator().get_schema(request=None, public=True)

    def test_required_features_path(self, schema):
        operation = schema["paths"]["/api/pim/admin/feature-sets/{idx}/required-features/"]["get"]

        assert operation["summary"]
        ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/RequiredFeatureListResponse")
        listing = schema["components"]["schemas"]["RequiredFeatureListResponse"]
        assert listing["type"] == "array"
        assert listing["items"]["$ref"].endswith("/RequiredFeatureResponse")
        assert "/api/pim/admin/{channel_idx}/feature-sets/{idx}/required-features/" in schema["paths"]

    def test_patch_operation(self, schema):
        operation = schema["paths"]["/api/pim/admin/feature-sets/{idx}/features/{feature_idx}/"]["patch"]

        assert operation["summary"]
        body = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        assert body.endswith("SetFeatureRequiredRequest")
        assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
            "FeatureInSetResponse"
        )

    def test_component_shapes(self, schema):
        components = schema["components"]["schemas"]

        assert {"is_required", "is_required_override"} <= set(components["FeatureInSetResponse"]["properties"])
        assert "is_required" in components["FeatureInSetEntry"]["properties"]
        required = components["PatchedSetFeatureRequiredRequest"]
        assert required["required"] == ["is_required"]
        assert set(components["RequiredFeatureResponse"]["properties"]) == {"feature", "source"}
        source = components["RequiredFeatureResponse"]["properties"]["source"]
        assert source["allOf"][0]["$ref"].endswith("/SourceEnum")
        assert components["SourceEnum"]["enum"] == ["system", "feature", "feature_set"]
