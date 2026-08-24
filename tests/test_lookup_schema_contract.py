# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract test for `schemas/responses/lookup.py`, the hand-mirrored django-lookup hit shape.

PIM never imports `django_lookup.schemas.responses.lookup` (a Pydantic annotation is resolved at
class definition time, which would make the optional module a hard dependency — see that module's
docstring). This test is the substitute: it compares field names against the real schema when the
sibling module happens to be importable (the zeno service container), and skips cleanly otherwise —
mirroring `pytest.importorskip("django_lookup")` in `test_lookup_bridge.py::TestBuildQueryContract`.
"""

import pytest

from django_pim.schemas.responses.lookup import LookupBasicResponse, LookupReasonResponse, PossibleDuplicateResponse


def _field_names(model) -> set[str]:
    return set(model.model_fields)


class TestLookupHitShapeContract:
    def test_possible_duplicate_matches_check_candidate_field_names(self):
        pytest.importorskip("django_lookup")
        from django_lookup.schemas.responses.lookup import CheckCandidate

        assert _field_names(PossibleDuplicateResponse) == _field_names(CheckCandidate)

    def test_basic_matches_basic_out_field_names(self):
        pytest.importorskip("django_lookup")
        from django_lookup.schemas.responses.lookup import BasicOut

        assert _field_names(LookupBasicResponse) == _field_names(BasicOut)

    def test_reason_matches_reason_out_field_names(self):
        pytest.importorskip("django_lookup")
        from django_lookup.schemas.responses.lookup import Observed, ReasonOut

        assert _field_names(LookupReasonResponse) == _field_names(ReasonOut)
        # `observed` mirrors `Observed` as a plain dict[str, str] — its two keys are the contract.
        assert _field_names(Observed) == {"query", "candidate"}

    def test_kind_and_decision_enums_are_str_subclasses(self):
        """`kind`/`decision` are bare `str` here on purpose (their enums live in the optional
        module — see the module docstring). Safe only as long as the real enums are str-valued.
        """
        pytest.importorskip("django_lookup")
        from django_lookup.enums import DecisionAuto, FingerprintKind

        assert issubclass(FingerprintKind, str)
        assert issubclass(DecisionAuto, str)
