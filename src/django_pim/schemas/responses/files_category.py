# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for file categories."""

from pydantic import BaseModel, ConfigDict, Field


class FilesCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Primary key", examples=[1])
    code: str = Field(description="Category code", examples=["manual"])
    name_t9n: dict = Field(description="Translated name JSON", examples=[{"en": "Manual", "pl": "Instrukcja"}])
    name: str = Field(description="Resolved name", examples=["Manual"])
    db_created: str = Field(description="Creation timestamp", examples=["2024-01-01T00:00:00Z"])


class FilesCategoryListResponse(BaseModel):
    count: int = Field(description="Total number of file categories", examples=[0, 4], ge=0)
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[FilesCategoryResponse] = Field(description="List of file category objects")
