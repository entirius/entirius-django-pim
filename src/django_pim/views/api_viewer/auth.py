# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Staff-only access for the legacy /api-viewer/ routes — the admin API's rule (staff or superuser, JWT)."""

from functools import wraps

from django_utils.api.exceptions import Forbidden, Unauthorized
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


def staff_required(view):
    """Authenticate the Bearer JWT and admit staff or superusers; place it inside `api_view`."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        try:
            result = JWTAuthentication().authenticate(request)
        except AuthenticationFailed as exc:
            raise Unauthorized(message="Invalid or expired token") from exc
        if result is None:
            raise Unauthorized(message="Authentication required")
        user = result[0]
        if not (user.is_staff or user.is_superuser):
            raise Forbidden(message="Staff only")
        request.user = user
        return view(request, *args, **kwargs)

    return _wrapped
