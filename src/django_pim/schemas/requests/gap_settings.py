# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schema for the quality-gaps settings endpoint (featureset-cascade etap-04)."""

from pydantic import BaseModel, Field


class UpdateGapSettingsRequest(BaseModel):
    """PATCH body for ``gaps/settings/``. Single-field surface — the flag is required."""

    gaps_skip_default_featureset: bool = Field(
        description=(
            "While a product is on the default (placeholder) feature set, report only the "
            "'assign a real feature set' gap and suppress all other checks."
        )
    )
