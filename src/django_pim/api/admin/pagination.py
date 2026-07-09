# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Pagination classes for admin API endpoints.
"""

from rest_framework.pagination import PageNumberPagination


class AdminPageNumberPagination(PageNumberPagination):
    """
    Page number pagination for admin APIs.

    Provides standard page-based pagination with configurable page size.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"
