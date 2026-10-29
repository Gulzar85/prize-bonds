from typing import Any

import structlog
from allauth.headless.contrib.rest_framework.authentication import JWTTokenAuthentication
from rest_framework.request import Request


class JWTAuthentication(JWTTokenAuthentication):  # type: ignore[misc]
    """allauth's JWT authentication that also tags every log line with the user id."""

    def authenticate(self, request: Request) -> Any:
        result = super().authenticate(request)
        if result is not None:
            structlog.contextvars.bind_contextvars(user_id=str(result[0].pk))
        return result
