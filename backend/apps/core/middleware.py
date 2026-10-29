import uuid

import structlog
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class RequestIDMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest) -> None:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.id = request_id  # type: ignore[attr-defined]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        if hasattr(request, "user") and request.user.is_authenticated:
            structlog.contextvars.bind_contextvars(user_id=str(request.user.pk))

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        request_id = getattr(request, "id", None)
        if request_id:
            response["X-Request-ID"] = request_id
        return response
