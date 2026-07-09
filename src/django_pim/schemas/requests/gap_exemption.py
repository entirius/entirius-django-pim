# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for gap exemptions (deep mute, etap-13 gap-spawn).

Shape only — sku/definition existence and language-served validation live in
``gap_exemption_service``.
"""

from pydantic import BaseModel, Field


class CreateGapExemptionRequest(BaseModel):
    """Mute one quality rule for one product (``language`` null = all languages)."""

    sku: str = Field(description="Product SKU on this channel", examples=["SKU-1"], min_length=1, max_length=255)
    definition_key: str = Field(
        description="Key of the rule to mute", examples=["pl-description"], min_length=1, max_length=64
    )
    language: str | None = Field(None, description="ISO2 language (null = all languages)", max_length=8)
    reason: str = Field("", description="Why this product is exempt", max_length=512)
