# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
from decimal import Decimal

from ..models import ProductPrice

logger = logging.getLogger(__name__)


class ProductPriceManager:
    def get(product, currency):
        return ProductPrice.objects.filter(product=product, currency=currency).first()

    def create(product, currency, price_brutto, special_price, special_price_from, special_price_to):
        price_brutto = Decimal(price_brutto)
        if special_price is None:
            special_price_from = None
            special_price_to = None
        else:
            special_price = Decimal(special_price)
        product_price = ProductPrice(
            product=product,
            currency=currency,
            price_brutto=price_brutto,
            special_price=special_price,
            special_price_from=special_price_from,
            special_price_to=special_price_to,
        )
        product_price.save()
        logger.info(f"New ProductPrice: {product} - {price_brutto} {currency}")
        return product_price

    def update(
        product_price,
        price_brutto=None,
        special_price=None,  # jak jest null to updatuje na null!
        special_price_from=None,
        special_price_to=None,
    ):
        to_save = False
        updated = []
        updated_txt = []
        if price_brutto is None:
            return
        price_brutto = Decimal(price_brutto)
        if product_price.price_brutto != price_brutto:
            updated.append("price_brutto")
            updated_txt.append('price_brutto "%s" => "%s"' % (product_price.price_brutto, price_brutto))
            product_price.price_brutto = price_brutto
            to_save = True
        if special_price is None:
            special_price_from = None
            special_price_to = None
        else:
            special_price = Decimal(special_price)
        if product_price.special_price != special_price:
            updated.append("special_price")
            updated_txt.append('special_price "%s" => "%s"' % (product_price.special_price, special_price))
            product_price.special_price = special_price
            to_save = True
        if product_price.special_price_from != special_price_from:
            updated.append("special_price_from")
            updated_txt.append(
                'special_price_from "%s" => "%s"' % (product_price.special_price_from, special_price_from)
            )
            product_price.special_price_from = special_price_from
            to_save = True
        if product_price.special_price_to != special_price_to:
            updated.append("special_price_to")
            updated_txt.append('special_price_to "%s" => "%s"' % (product_price.special_price_to, special_price_to))
            product_price.special_price_to = special_price_to
            to_save = True
        if to_save:
            product_price.save(update_fields=updated)
            logger.info("ProductPrice [%s] updated fields: (%s)", product_price.id, ", ".join(updated_txt))

    def get_or_create(
        product, currency, price_brutto, special_price=None, special_price_from=None, special_price_to=None, update=True
    ):
        product_price = ProductPriceManager.get(product, currency)
        if product_price is None:
            product_price = ProductPriceManager.create(
                product, currency, price_brutto, special_price, special_price_from, special_price_to
            )
            created = True
        else:
            if update:
                ProductPriceManager.update(
                    product_price, price_brutto, special_price, special_price_from, special_price_to
                )
            created = False
        return (product_price, created)

    def delete(product, currencies):
        ProductPrice.objects.filter(product=product, currency__in=currencies).delete()

    def delete_exludes(product, exlude_currencies):
        ProductPrice.objects.filter(product=product).exclude(currency__in=exlude_currencies).delete()
