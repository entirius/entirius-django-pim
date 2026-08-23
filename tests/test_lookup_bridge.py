# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the django-lookup create hook (plan 07).

Three hook states, all driven through `sys.modules` so the suite behaves the same whether or not
the optional module happens to be importable next to PIM (it is in the zeno service container, it
is not in a bare checkout): `_install_fake_lookup` mirrors the real contract dataclasses
(`django_lookup.services.lookup_service.Hit`), `_block_lookup` makes the import fail the way an
uninstalled module does.
"""

import sys
import types
from dataclasses import dataclass, field

import pytest

from django_pim.schemas.requests.product import CreateProductRequest, ProductAttributeValueRequest
from django_pim.services import lookup_bridge

CHANNEL = "test-shop"
PRODUCTS_URL = f"/api/pim/admin/{CHANNEL}/products/"
_LOOKUP_MODULES = (
    "django_lookup",
    "django_lookup.enums",
    "django_lookup.schemas",
    "django_lookup.schemas.requests",
    "django_lookup.schemas.requests.lookup",
    "django_lookup.services",
    "django_lookup.services.lookup_service",
)


# --------------------------------------------------------------------------------------------
# Fake django_lookup — the shape `lookup_service.check` really returns
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Reason:
    code: str
    label: str
    score: int
    observed: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _Hit:
    kind: str
    ref: str
    similarity: int
    score: int
    decision: str
    reasons: list = field(default_factory=list)
    basic: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _CheckResult:
    decision: str
    parsed: dict
    candidates: list
    warnings: list = field(default_factory=list)


def _hit(ref="ATLAS-1", kind="atlas_source_product"):
    return _Hit(
        kind=kind,
        ref=ref,
        similarity=60,
        score=82,
        decision="review",
        reasons=[
            _Reason(
                code="gtin_exact",
                label="GTIN 05901234123457 identical",
                score=60,
                observed={"query": "05901234123457", "candidate": "05901234123457"},
            )
        ],
        basic={
            "sku": ref,
            "name": "Drill GSR 12V-35",
            "brand": "Bosch",
            "ean": "5901234123457",
            "main_image_url": "",
            "detail_url": f"/api/atlas/v2/admin/source-products/{ref}/",
        },
    )


def _install_fake_lookup(monkeypatch, check):
    """Inject a minimal `django_lookup` package; `check` records its call and answers."""
    calls = []

    def _check(query, user=None, image_data=None, source="api_check"):
        calls.append({"query": query, "user": user, "source": source})
        return check(query)

    class _LookupQuery:
        def __init__(self, **fields):
            self.fields = fields

    class _DecisionSource:
        CREATE_HOOK = "create_hook"

    modules = {name: types.ModuleType(name) for name in _LOOKUP_MODULES}
    modules["django_lookup.enums"].DecisionSource = _DecisionSource
    modules["django_lookup.schemas.requests.lookup"].LookupQuery = _LookupQuery
    modules["django_lookup.services.lookup_service"].check = _check
    modules["django_lookup.services"].lookup_service = modules["django_lookup.services.lookup_service"]
    modules["django_lookup.schemas.requests"].lookup = modules["django_lookup.schemas.requests.lookup"]
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return calls


def _block_lookup(monkeypatch):
    """`None` in `sys.modules` makes the import fail exactly like an uninstalled distribution."""
    for name in _LOOKUP_MODULES:
        monkeypatch.setitem(sys.modules, name, None)


def _request(**overrides):
    fields = {"sku": "NEW-1", "feature_set_idx": "test-set"} | overrides
    return CreateProductRequest(**fields)


def _attribute(feature_idx, **values):
    return ProductAttributeValueRequest(feature_idx=feature_idx, **values)


# --------------------------------------------------------------------------------------------
# build_query — pure, no lookup module needed
# --------------------------------------------------------------------------------------------


class TestBuildQuery:
    def test_takes_ean_name_brand_mpn_and_physicals(self):
        request = _request(
            ean="5901234123457",
            weight="1.50",
            width="30.00",
            attributes=[
                _attribute("name", value_txt_t9n={"pl": "Wiertarka", "en": "Drill"}),
                _attribute("brand", value_txt_t9n={"pl": "Bosch"}),
                _attribute("mpn", value_txt="GSR 12V-35"),
            ],
        )

        query = lookup_bridge.build_query(request, "pl")

        assert query == {
            "ean": "5901234123457",
            "name": "Wiertarka",
            "brand": "Bosch",
            "mpn": "GSR 12V-35",
            "attrs": {"weight": "1.50", "width": "30.00"},
            "limit": lookup_bridge.LOOKUP_LIMIT,
        }

    def test_leaves_scope_out_so_lookup_searches_every_kind(self):
        assert "scope" not in lookup_bridge.build_query(_request(ean="5901234123457"), "pl")

    def test_falls_back_to_another_language_when_the_channel_one_is_missing(self):
        request = _request(attributes=[_attribute("name", value_txt_t9n={"en": "Drill", "de": ""})])

        assert lookup_bridge.build_query(request, "pl")["name"] == "Drill"

    def test_drops_empty_signals(self):
        request = _request(attributes=[_attribute("name", value_txt_t9n={"pl": "   "})])

        assert lookup_bridge.build_query(request, "pl") == {"limit": lookup_bridge.LOOKUP_LIMIT}

    def test_ignores_attributes_of_other_features(self):
        request = _request(attributes=[_attribute("color", value_txt="red")])

        assert "name" not in lookup_bridge.build_query(request, "pl")


# --------------------------------------------------------------------------------------------
# possible_duplicates — the three hook states
# --------------------------------------------------------------------------------------------


class TestPossibleDuplicates:
    def test_lookup_present_returns_scored_candidates(self, monkeypatch):
        calls = _install_fake_lookup(
            monkeypatch, lambda query: _CheckResult(decision="review", parsed={}, candidates=[_hit()])
        )

        duplicates, warnings = lookup_bridge.possible_duplicates(_request(ean="5901234123457"), "pl", user=None)

        assert warnings == []
        assert [(hit.kind, hit.ref, hit.score, hit.decision) for hit in duplicates] == [
            ("atlas_source_product", "ATLAS-1", 82, "review")
        ]
        assert duplicates[0].reasons[0].code == "gtin_exact"
        assert duplicates[0].basic.brand == "Bosch"
        assert calls[0]["query"].fields["limit"] == lookup_bridge.LOOKUP_LIMIT

    def test_passes_the_lookup_warnings_through(self, monkeypatch):
        _install_fake_lookup(
            monkeypatch,
            lambda query: _CheckResult(
                decision="no_match", parsed={}, candidates=[], warnings=["image_layer_unavailable"]
            ),
        )

        duplicates, warnings = lookup_bridge.possible_duplicates(_request(ean="5901234123457"), "pl")

        assert (duplicates, warnings) == ([], ["image_layer_unavailable"])

    def test_lookup_absent_returns_no_candidates_and_a_warning(self, monkeypatch):
        _block_lookup(monkeypatch)

        duplicates, warnings = lookup_bridge.possible_duplicates(_request(ean="5901234123457"), "pl")

        assert (duplicates, warnings) == ([], [lookup_bridge.WARNING_LOOKUP_UNAVAILABLE])

    def test_failing_lookup_degrades_to_a_warning(self, monkeypatch):
        def _boom(query):
            raise RuntimeError("provider exploded")

        _install_fake_lookup(monkeypatch, _boom)

        duplicates, warnings = lookup_bridge.possible_duplicates(_request(ean="5901234123457"), "pl")

        assert (duplicates, warnings) == ([], [lookup_bridge.WARNING_LOOKUP_FAILED])

    def test_a_hit_that_does_not_match_the_contract_is_a_warning_not_a_crash(self, monkeypatch):
        broken = _Hit(kind="pim_product", ref="X", similarity=1, score=1, decision="review", basic={})
        _install_fake_lookup(monkeypatch, lambda query: _CheckResult("review", {}, [broken]))

        duplicates, warnings = lookup_bridge.possible_duplicates(_request(ean="5901234123457"), "pl")

        assert (duplicates, warnings) == ([], [lookup_bridge.WARNING_LOOKUP_FAILED])

    def test_a_create_without_any_identifying_signal_never_calls_lookup(self, monkeypatch):
        calls = _install_fake_lookup(monkeypatch, lambda query: _CheckResult("no_match", {}, []))

        duplicates, warnings = lookup_bridge.possible_duplicates(_request(weight="1.50"), "pl")

        assert (duplicates, warnings, calls) == ([], [], [])

    def test_the_setting_switches_the_hook_off(self, monkeypatch):
        calls = _install_fake_lookup(monkeypatch, lambda query: _CheckResult("review", {}, [_hit()]))
        monkeypatch.setattr("django_pim.settings.PIM_LOOKUP_ON_CREATE", False)

        duplicates, warnings = lookup_bridge.possible_duplicates(_request(ean="5901234123457"), "pl")

        assert (duplicates, warnings, calls) == ([], [], [])


# --------------------------------------------------------------------------------------------
# The endpoint — create never blocks, the answer carries the candidates
# --------------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreateHookEndpoint:
    @pytest.fixture(autouse=True)
    def channel(self, authenticated_client):
        from tests.factories import ChannelFactory, FeatureSetFactory

        ChannelFactory(idx=CHANNEL)
        FeatureSetFactory(idx="test-set", name="Test Set")

    def _create(self, client, **overrides):
        body = {"sku": "HOOK-1", "feature_set_idx": "test-set", "ean": "5901234123457"} | overrides
        return client.post(PRODUCTS_URL, body, format="json")

    def test_create_returns_201_with_possible_duplicates(self, authenticated_client, monkeypatch):
        calls = _install_fake_lookup(
            monkeypatch, lambda query: _CheckResult(decision="review", parsed={}, candidates=[_hit()])
        )

        response = self._create(authenticated_client)

        assert response.status_code == 201
        payload = response.json()
        assert payload["sku"] == "HOOK-1"
        assert payload["lookup_warnings"] == []
        assert [(hit["kind"], hit["ref"], hit["decision"]) for hit in payload["possible_duplicates"]] == [
            ("atlas_source_product", "ATLAS-1", "review")
        ]
        assert calls[0]["query"].fields["ean"] == "5901234123457"
        assert calls[0]["user"].is_staff  # the decision log records who was shown the candidates
        assert calls[0]["source"] == "create_hook"  # plan 07 binding: DedupDecision(source="create_hook")

    def test_create_still_201_when_lookup_is_absent(self, authenticated_client, monkeypatch):
        _block_lookup(monkeypatch)

        response = self._create(authenticated_client)

        assert response.status_code == 201
        payload = response.json()
        assert payload["possible_duplicates"] == []
        assert payload["lookup_warnings"] == [lookup_bridge.WARNING_LOOKUP_UNAVAILABLE]

    def test_create_still_201_when_lookup_raises(self, authenticated_client, monkeypatch):
        def _boom(query):
            raise RuntimeError("provider exploded")

        _install_fake_lookup(monkeypatch, _boom)

        response = self._create(authenticated_client, sku="HOOK-2")

        assert response.status_code == 201
        assert response.json()["lookup_warnings"] == [lookup_bridge.WARNING_LOOKUP_FAILED]

    def test_detail_get_carries_no_duplicate_block(self, authenticated_client, monkeypatch):
        _block_lookup(monkeypatch)
        self._create(authenticated_client, sku="HOOK-3")

        payload = authenticated_client.get(f"{PRODUCTS_URL}HOOK-3/").json()

        assert (payload["possible_duplicates"], payload["lookup_warnings"]) == ([], [])
