# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for files and product files."""

from pydantic import BaseModel, ConfigDict, Field


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="File primary key", examples=[1])
    sha1: str | None = Field(description="SHA1 hash of the file", examples=["da39a3ee5e6b4b0d3255bfef95601890afd80709"])
    file_type: int = Field(
        description="File type enum value (0=undefined, 1=picture, 2=pdf, 3=doc, 4=video)", examples=[2]
    )
    file_type_name: str = Field(description="File type display name", examples=["PDF File Type"])
    original_file_name: str | None = Field(description="Original uploaded file name", examples=["manual.pdf"])
    file_label: str | None = Field(description="Custom label for the file", examples=["Product Manual v2"])
    file_label_t9n: dict = Field(
        default_factory=dict, description="Multilingual file label", examples=[{"en": "Manual", "pl": "Instrukcja"}]
    )
    file_url: str = Field(description="URL to the file", examples=["/media/files/abc123.pdf"])
    category_code: str | None = Field(description="File category code", examples=["manual"])
    category_name: str | None = Field(description="File category display name", examples=["Manual"])
    db_created: str = Field(description="Creation timestamp", examples=["2024-01-01T00:00:00Z"])


class ProductFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="ProductFile primary key", examples=[1])
    file: FileResponse = Field(description="File details")


class ProductFileListResponse(BaseModel):
    count: int = Field(description="Total number of product files", examples=[0, 3], ge=0)
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[ProductFileResponse] = Field(description="List of product file objects")
