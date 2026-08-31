# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Mirror of a django-lookup hit — the `possible_duplicates` block of the product create response.

django-lookup is optional, so PIM never imports it to declare a schema (a Pydantic annotation is
resolved at class definition time, which would turn the module into a hard dependency and make the
OpenAPI document depend on the deployment). The shape is mirrored here the same way
`services/lookup_provider.py` mirrors the provider contract; `django_lookup.schemas.responses.lookup`
is authoritative for the field names. `kind`, `match` and `decision` stay plain strings because their
enums live in the optional module.
"""

from pydantic import BaseModel, Field


class LookupReasonResponse(BaseModel):
    """One piece of evidence behind a candidate — a reviewer must see why it is proposed."""

    code: str = Field(description="Stable machine code of the evidence", examples=["gtin_exact"])
    label: str = Field(description="Human-readable explanation", examples=["GTIN 05901234123457 identical"])
    score: int = Field(description="Points this evidence contributed (may be negative)", examples=[60])
    observed: dict[str, str] = Field(
        default_factory=dict,
        description="Both sides of the comparison",
        examples=[{"query": "05901234123457", "candidate": "05901234123457"}],
    )


class LookupBasicResponse(BaseModel):
    """Inline display data of a candidate — never a full payload, details live behind `detail_url`."""

    sku: str = Field(description="Catalog reference (PIM sku, atlas `<source>:<external_id>`)")
    name: str = Field("", description="Candidate name in its catalog's default language")
    brand: str = Field("", description="Brand as stored in that catalog")
    ean: str = Field("", description="GTIN as stored in that catalog")
    main_image_url: str = Field("", description="Main picture, empty when the candidate has none")
    detail_url: str = Field("", description="Admin API deep link of the catalog owning the candidate")


class PossibleDuplicateResponse(BaseModel):
    """A product the catalogs already hold that looks like the one just created."""

    kind: str = Field(description="Catalog the candidate comes from", examples=["pim_product", "atlas_source_product"])
    ref: str = Field(description="Reference inside that catalog", examples=["PROD-001"])
    similarity: int = Field(
        description=(
            "Relevance to the query as given, 0-100: a photo-only query is judged by the photo, a text-only "
            "query by identifier/name, both by a fixed blend. Not the dedup score."
        ),
        examples=[100],
    )
    match: str = Field(
        description="`exact`: same identifier or the same picture file; `similar`: something agreed; `none`: nothing did",
        examples=["exact"],
    )
    score: int = Field(description="Total evidence, clamped to 0-100", examples=[82])
    decision: str = Field(description="Verdict for this candidate: match | review | no_match", examples=["review"])
    reasons: list[LookupReasonResponse] = Field(default_factory=list, description="Evidence, strongest first")
    basic: LookupBasicResponse = Field(description="Inline display data")
