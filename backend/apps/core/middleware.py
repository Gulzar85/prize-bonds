import uuid

import structlog
from django.utils.deprecation import MiddlewareMixin


class RequestIDMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        if hasattr(request, "user") and request.user.is_authenticated:
            structlog.contextvars.bind_contextvars(user_id=str(request.user.id))

    def process_response(self, request, response):
        if hasattr(request, "id"):
            response["X-Request-ID"] = request.id
        return response
