# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Shared error helpers for admin API views.

Provides safe 500 responses that log full details server-side
without leaking DB names, paths, or SQL fragments to callers.
"""

import traceback
import uuid

from process_logger import ProcessLogger
from rest_framework import status
from rest_framework.response import Response


def not_found_response(detail: str) -> Response:
    """Standard 404 response for missing resources."""
    return Response({"detail": detail}, status=status.HTTP_404_NOT_FOUND)


def internal_error(exc: Exception) -> Response:
    """Log exception with structured trace context; return opaque 500 response."""
    error_id = uuid.uuid4().hex[:8]

    logger = ProcessLogger(process_name="api_error", module="admin_api")
    logger.add_log_param_once("error_id", error_id)

    if exc.__traceback__:
        frames = traceback.extract_tb(exc.__traceback__)
        if frames:
            f = frames[-1]
            logger.add_log_param_once("origin_file", f.filename.rsplit("/", 1)[-1])
            logger.add_log_param_once("origin_func", f.name)
            logger.add_log_param_once("origin_line", f.lineno)

    logger.exception(exc)

    return Response(
        {"detail": f"Internal server error [{error_id}]"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
