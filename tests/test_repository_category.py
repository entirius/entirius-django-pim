# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`DjangoPimRepository.category_update_or_create` description merging.

A feed that carries no category copy (empty dict, blank string, or a single
locale) must not wipe descriptions already stored for the category — the
import merges per locale instead of replacing the whole `description_t9n`.
"""

import pytest

from django_pim.models import ProductCategory
from django_pim.repository.repository import DjangoPimRepository
from tests.factories import ChannelFactory, CurrencyFactory, LanguageFactory, ProductCategoryFactory

pytestmark = pytest.mark.django_db


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def channel(db):
    return ChannelFactory(
        idx="novatrade",
        default_language=LanguageFactory(iso2="EN", iso3="ENG"),
        default_currency=CurrencyFactory(iso3="EUR"),
    )


@pytest.fixture
def repository(channel):
    repository = DjangoPimRepository()
    repository.set_shop(channel.idx)
    repository.locale = "en"
    return repository


@pytest.fixture
def category(channel):
    return ProductCategoryFactory(
        shop=channel,
        idx="workwear",
        name_t9n={"en": "Workwear"},
        description_t9n={"en": "Kestrel Supply workwear", "pl": "Odziez robocza Kestrel Supply"},
        url_key_t9n={"en": "workwear"},
    )


def _stored_description_t9n(category: ProductCategory) -> dict[str, str]:
    return ProductCategory.objects.get(pk=category.pk).description_t9n


# --- description merging ------------------------------------------------------


def test_empty_description_t9n_keeps_stored_descriptions(repository, category):
    repository.category_update_or_create(
        idx="workwear", name="Workwear", url_key_t9n={"en": "workwear"}, description_t9n={}
    )

    assert _stored_description_t9n(category) == {
        "en": "Kestrel Supply workwear",
        "pl": "Odziez robocza Kestrel Supply",
    }


def test_missing_description_t9n_keeps_stored_descriptions(repository, category):
    repository.category_update_or_create(idx="workwear", name="Workwear", url_key_t9n={"en": "workwear"})

    assert _stored_description_t9n(category) == {
        "en": "Kestrel Supply workwear",
        "pl": "Odziez robocza Kestrel Supply",
    }


def test_blank_description_value_keeps_stored_description_for_that_locale(repository, category):
    repository.category_update_or_create(
        idx="workwear", name="Workwear", url_key_t9n={"en": "workwear"}, description_t9n={"en": ""}
    )

    assert _stored_description_t9n(category)["en"] == "Kestrel Supply workwear"


def test_single_locale_description_t9n_leaves_other_locales_intact(repository, category):
    repository.category_update_or_create(
        idx="workwear",
        name="Workwear",
        url_key_t9n={"en": "workwear"},
        description_t9n={"en": "ENT-4400 workwear range"},
    )

    assert _stored_description_t9n(category) == {
        "en": "ENT-4400 workwear range",
        "pl": "Odziez robocza Kestrel Supply",
    }
