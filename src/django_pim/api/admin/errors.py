# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Shared error helpers for admin API views.

Views raise DRF exceptions and the service's v2 exception handler builds the
error body. The helpers here cover what that handler does not: a conflict
exception, a query-parameter error that names its location, a module refusal
(``ClientError``) answered with the message the module wrote for the client, and
a safe 500 that logs full details server-side without leaking DB names, paths,
or SQL fragments to callers.
"""

import traceback
import uuid
from typing import NoReturn

from django_utils.api.v2_errors import ErrorDetail, ErrorResponse
from process_logger import ProcessLogger
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from django_pim.exceptions import ClientError


class Conflict(APIException):
    """409: the request conflicts with the current state; the v2 handler keeps the message."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


def query_param_error(param: str, message: str) -> ValidationError:
    """400 on one query parameter: ``details[]`` names it, with location ``query`` (django-utils >= 2.4.0)."""
    exc = ValidationError({param: [message]})
    exc.location = "query"
    return exc


def int_query_param(raw: str | None, param: str, minimum: int | None = None) -> int | None:
    """An optional integer query parameter: ``None`` when absent, a 400 naming ``param`` when not an integer
    or below ``minimum``."""
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise query_param_error(param, f"Invalid {param} parameter: must be an integer") from None
    if minimum is not None and value < minimum:
        raise query_param_error(param, f"Invalid {param} parameter: must be at least {minimum}")
    return value


def raise_client_error(exc: ClientError, error_class: type[APIException] = ValidationError) -> NoReturn:
    """Re-raise a module refusal as ``error_class`` (400 by default) carrying only ``exc.client_message``.

    Views catch ``InvalidRequestError``, never a bare ``ValueError``: the text of an
    exception from a lower layer must not reach the client; the v2 handler answers it with a 500.
    """
    raise error_class(exc.client_message) from exc


def internal_error(exc: Exception) -> Response:
    """Log exception with structured trace context; return opaque 500 in the v2 envelope.

    The ``debug_id`` the caller gets is the ``error_id`` of the log line.

    A DRF ``APIException`` (e.g. ``NotFound`` for a page out of range) is not an
    internal error: it is re-raised so the service exception handler answers it
    with its own status in the v2 envelope.
    """
    if isinstance(exc, APIException):
        raise exc
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

    body = ErrorResponse(error="INTERNAL_ERROR", message="An internal error occurred.", debug_id=error_id)
    return Response(body.model_dump(), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def validation_error_response(message: str, details: list[ErrorDetail]) -> Response:
    """400 in the v2 error shape: ``{error, message, debug_id, details[]}``."""
    body = ErrorResponse(error="VALIDATION_ERROR", message=message, debug_id=uuid.uuid4().hex[:8], details=details)
    return Response(body.model_dump(), status=status.HTTP_400_BAD_REQUEST)
