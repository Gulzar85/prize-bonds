import re
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

# (scope, regex on the request path). Scopes map to settings.AUTH_THROTTLE_RATES.
AUTH_ENDPOINTS = [
    ("login", re.compile(r"^/api/v1/auth/(app|browser)/v1/auth/login$")),
    ("signup", re.compile(r"^/api/v1/auth/(app|browser)/v1/auth/signup$")),
    ("password_reset", re.compile(r"^/api/v1/auth/(app|browser)/v1/auth/password/request$")),
    ("mfa", re.compile(r"^/api/v1/auth/(app|browser)/v1/(auth/2fa/authenticate|account/authenticators/.*)$")),
]
_PERIODS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_rate(rate: str) -> tuple[int, int]:
    count, period = rate.split("/")
    return int(count), _PERIODS[period]


def client_ip(request: HttpRequest) -> str:
    return str(request.META.get("REMOTE_ADDR", "unknown"))


class AuthEndpointThrottleMiddleware:
    """Per-IP throttle for allauth headless auth endpoints (which are not DRF views)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            path = request.path.rstrip("/")
            for scope, pattern in AUTH_ENDPOINTS:
                if pattern.match(path):
                    limit, window = parse_rate(settings.AUTH_THROTTLE_RATES[scope])
                    key = f"throttle:{scope}:{client_ip(request)}"
                    cache.add(key, 0, timeout=window)
                    if cache.incr(key) > limit:
                        response = JsonResponse(
                            {
                                "type": "https://prizebonds.example/problems/throttled",
                                "title": "Too Many Requests",
                                "status": 429,
                                "detail": "Request was throttled.",
                            },
                            status=429,
                            content_type="application/problem+json",
                        )
                        response["Retry-After"] = str(window)
                        return response
                    break
        return self.get_response(request)
