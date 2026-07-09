# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime
from typing import Any

from django_regional.models import Country
from django_utils.domains.domain import Domain
from process_logger import ProcessLogger

from django_pim.models import Shop
from django_pim.repository import DjangoPimRepository


class DomainPim(Domain):
    shop: Shop
    locales: list = []
    pim_repository: DjangoPimRepository
    updated_at: datetime
    countries_cache: dict[str, Country] = {}

    def __init__(self):
        self.pim_repository = DjangoPimRepository()

    def set_logger(self, logger: ProcessLogger) -> None:
        super().set_logger(logger)
        self.pim_repository.set_logger(logger)

    def set_shop(self, shop: Shop) -> None:
        self.shop = shop
        self.locales = self.get_locales()
        self.pim_repository.shop = shop

    def get_locales(self) -> list:
        if self.shop:
            languages = self.shop.languages.all()
            return [language.iso2 for language in languages]
        else:
            return []

    def set_updated_at(self, updated_at: datetime) -> None:
        self.updated_at = updated_at

    def _get_expected_currency_for_country(self, country_code: str) -> Any | None:
        """
        Get expected currency for a given country code.
        Uses the same mapping as in DomainPricesMagento._get_currency_by_country
        """

        if len(self.countries_cache) < 1:
            for country in Country.objects.all():
                self.countries_cache[country.iso2] = country

        if country_code in self.countries_cache and self.countries_cache[country_code] is not None:
            return self.countries_cache[country_code].default_currency.iso3
        else:
            return "EUR"
