from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://prizebonds.example/problems/"


class DomainError(Exception):
    """Business-rule violation raised by services; mapped to a 409 problem."""

    code = "domain_error"
    detail = "The request violates a business rule."


def _problem(exc: Exception, response: Response, request: Any) -> dict[str, Any]:
    code = getattr(exc, "default_code", "error")
    data = response.data
    detail = data.get("detail") if isinstance(data, dict) else None
    body: dict[str, Any] = {
        "type": f"{PROBLEM_TYPE_BASE}{code}",
        "title": response.status_text,
        "status": response.status_code,
        "detail": str(detail) if detail is not None else str(exc),
    }
    if isinstance(exc, APIException) and isinstance(exc.detail, dict | list) and detail is None:
        body["errors"] = exc.detail
    request_id = getattr(request, "id", None)
    if request_id:
        body["request_id"] = request_id
    return body


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        response = Response({"detail": exc.detail}, status=status.HTTP_409_CONFLICT)
        response.data = {
            "type": f"{PROBLEM_TYPE_BASE}{exc.code}",
            "title": "Conflict",
            "status": 409,
            "detail": exc.detail,
        }
    else:
        handled = exception_handler(exc, context)
        if handled is None:
            return None
        response = handled
        response.data = _problem(exc, response, context.get("request"))
    response.content_type = PROBLEM_CONTENT_TYPE
    return response
