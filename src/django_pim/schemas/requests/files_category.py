# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for file categories."""

from pydantic import BaseModel, Field


class CreateFilesCategoryRequest(BaseModel):
    code: str = Field(description="Category code identifier", examples=["manual"], min_length=1, max_length=256)
    name_t9n: dict = Field(description="Translated name JSON", examples=[{"en": "Manual", "pl": "Instrukcja"}])


class UpdateFilesCategoryRequest(BaseModel):
    name_t9n: dict | None = Field(None, description="Translated name JSON", examples=[{"en": "User Manual"}])
