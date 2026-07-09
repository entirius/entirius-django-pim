# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Permission classes for django-pim Admin API.

Defines authorization rules for administrative operations.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView


class IsAdminUser(IsAuthenticated):
    """
    Permission for PIM admin API.

    Requires authenticated user with admin/staff privileges.
    User must have is_staff=True or is_superuser=True.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has admin permissions.

        Args:
            request: DRF request object
            view: View being accessed

        Returns:
            True if user is authenticated and has admin privileges
        """
        if not super().has_permission(request, view):
            return False

        return request.user.is_staff or request.user.is_superuser
