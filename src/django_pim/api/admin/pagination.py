# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Pagination classes for admin API endpoints.
"""

from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request


class AdminPageNumberPagination(PageNumberPagination):
    """
    Page number pagination for admin APIs.

    Provides standard page-based pagination with configurable page size.
    A page out of range raises DRF ``NotFound``; a ``page_size`` that is not a
    positive integer raises ``ValidationError`` instead of falling back silently
    (the fallback kept the bad value in the ``next`` / ``previous`` links).
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def get_page_size(self, request: Request) -> int:
        raw = request.query_params.get(self.page_size_query_param)
        if not raw:
            return self.page_size
        if not (raw.isascii() and raw.isdigit()) or int(raw) == 0:
            raise ValidationError({self.page_size_query_param: ["A positive integer is required."]})
        return min(int(raw), self.max_page_size)
