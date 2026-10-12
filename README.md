# entirius-django-pim

A Django module for product information of Entirius, the open-source modular ecommerce platform: the product
catalog behind every sales channel. It stores products, categories, features, attributes and media, and serves them
to the admin CMS over a REST API.

[![PyPI](https://img.shields.io/pypi/v/entirius-django-pim.svg)](https://pypi.org/project/entirius-django-pim/)
[![Python](https://img.shields.io/pypi/pyversions/entirius-django-pim.svg)](https://pypi.org/project/entirius-django-pim/)
[![License: MPL-2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](https://github.com/entirius/entirius-django-pim/blob/develop/LICENSE)

## What it does

- Stores products per sales channel on top of one shared physical product (SKU, EAN, dimensions).
- Models simple, configurable, bundle and custom products, with categories, features, feature sets and attributes.
- Manages pictures, files, videos and product links.
- Lets products on secondary channels inherit attributes, descriptions and media from a default channel.
- Reports quality gaps: what each product is missing, per channel and language, by configurable rules.
- Exposes an admin REST API with an OpenAPI schema.

## Installation

```shell
uv add entirius-django-pim
pip install entirius-django-pim
```

```python
INSTALLED_APPS = [
    ...
    "rest_framework",
    "django_regional",
    "django_pim",
]

# urls.py
urlpatterns = [
    path("", include("django_pim.urls")),
]
```

The module reads `MEDIA_URL`, `STATIC_URL` and `TMP_DIR` (a directory for file and picture processing) from the
project settings at import time. Optional settings (`T9N_DEFAULT_LANG`, `DEFAULT_CURRENCY`, `THUMBS_CONFIG`,
`PIM_GAPS_QUEUE` and others) and their defaults are in
https://github.com/entirius/entirius-django-pim/blob/develop/src/django_pim/settings.py

## Quick start

```python
from django_pim.services.product_service import get_product_by_sku

product = get_product_by_sku(channel_idx="default", sku="SKU-001")
print(product.visibility, product.is_enabled)
```

## Requirements

- Python 3.11 or newer, Django 5.0 or newer.
- PostgreSQL 15 or newer (`UniqueConstraint(nulls_distinct=False)`).
- Entirius packages pulled in: `entirius-django-regional`, `entirius-django-utils`, `entirius-py-bievents`,
  `entirius-py-idx-normalizator`, `entirius-py-int-enum-choices`, `entirius-py-image-transformations`,
  `entirius-py-process-logger`.

## Documentation

- Module docs: https://github.com/entirius/entirius-django-pim/tree/develop/docs
- Entirius documentation: https://docs.entirius.com/
- Changelog: https://github.com/entirius/entirius-django-pim/blob/develop/CHANGELOG.md

## Part of Entirius

This module runs inside the Entirius backend service (Volkanos) and is the catalog most other modules build on.

- Backend service: https://github.com/entirius/entirius-service-volkanos
- Docker harness: https://github.com/entirius/entirius-zeno
- Sibling modules: https://github.com/entirius/entirius-django-regional,
  https://github.com/entirius/entirius-django-utils, https://github.com/entirius/entirius-django-contentdb

## Development

```shell
make install     # sync dependencies (uv)
make check       # lint + format check (ruff)
make test        # test suite (pytest + pytest-django, needs PostgreSQL via DATABASE_URL)
```

Development and agent instructions: https://github.com/entirius/entirius-django-pim/blob/develop/AGENTS.md

## License

Mozilla Public License 2.0 (MPL-2.0) — see https://github.com/entirius/entirius-django-pim/blob/develop/LICENSE.
