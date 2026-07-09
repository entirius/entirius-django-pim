# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
FilesCategory service layer for business logic.

CRUD operations for file categories (manual, datasheet, certificate, etc.).
"""

from django.db.models import Q, QuerySet

from .. import settings
from ..models import FilesCategory

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "code": "code",
    "-code": "-code",
}


def list_files_categories(search: str | None = None, ordering: str | None = None) -> QuerySet[FilesCategory]:
    """
    List file categories with optional filtering.

    Args:
        search: Search term for code/name filtering (case-insensitive)
        ordering: Field to order by (default: code)
    """
    queryset = FilesCategory.objects.all()

    if search:
        queryset = queryset.filter(Q(code__icontains=search) | Q(name_t9n__icontains=search))

    order_field = ORDERING_MAP.get(ordering, "code") if ordering else "code"
    queryset = queryset.order_by(order_field)

    return queryset


def get_files_category_by_code(code: str) -> FilesCategory:
    """
    Get a single file category by code.

    Raises:
        FilesCategory.DoesNotExist: If not found
    """
    return FilesCategory.objects.get(code=code)


def resolve_files_category_name(category: FilesCategory, language: str | None = None) -> str:
    """Resolve file category name from translation JSON."""
    if language is None:
        language = settings.T9N_DEFAULT_LANG

    langs = [language]
    if language != settings.T9N_DEFAULT_LANG:
        langs.append(settings.T9N_DEFAULT_LANG)

    for lang in langs:
        if lang in category.name_t9n:
            name = category.name_t9n[lang]
            if name is not None:
                name = str(name).strip()
                if len(name) > 0:
                    return name

    return category.code


def create_files_category(code: str, name_t9n: dict) -> FilesCategory:
    """Create a new file category."""
    if FilesCategory.objects.filter(code=code).exists():
        raise ValueError(f"FilesCategory with code '{code}' already exists")

    return FilesCategory.objects.create(code=code, name_t9n=name_t9n)


def update_files_category(code: str, **fields: object) -> FilesCategory:
    """Update a file category by code."""
    category = FilesCategory.objects.get(code=code)
    for field, value in fields.items():
        if value is not None:
            setattr(category, field, value)
    category.save()
    return category


def delete_files_category(code: str) -> dict:
    """Delete a file category by code."""
    category = FilesCategory.objects.get(code=code)
    _, deleted_detail = category.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result
