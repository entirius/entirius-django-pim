# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for product files."""

from pydantic import BaseModel, Field


class LinkFileRequest(BaseModel):
    file_pk: int = Field(description="Primary key of an existing File to link", examples=[1])


class UpdateFileRequest(BaseModel):
    file_label_t9n: dict | None = Field(
        None, description="Multilingual file label", examples=[{"en": "Manual", "pl": "Instrukcja"}]
    )
    file_category_code: str | None = Field(None, description="Category code (null to clear)", examples=["manual"])
