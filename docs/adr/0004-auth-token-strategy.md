# ADR-0004: Authentication Token Strategy

## Status
Accepted (revised after verifying the installed allauth 65.21)

## Context
Web, Android and desktop clients need token auth; the Django admin needs session auth. django-allauth headless
handles signup, verification, login, password reset and MFA.

## Decision
- **Use allauth headless' built-in JWT strategy** (`HEADLESS_TOKEN_STRATEGY =
  allauth.headless.tokens.strategies.jwt.JWTTokenStrategy`). The spec allows a custom SimpleJWT strategy only if
  the installed allauth has no JWT support; 65.21 does, so `djangorestframework-simplejwt` was removed.
- Access token 15 min, refresh token 30 days, refresh rotation on (a used refresh token is rejected), RS256 signed
  with `JWT_PRIVATE_KEY` (env, PEM). Stateful validation is enabled: logout or session revocation invalidates
  both the access and refresh tokens immediately.
- DRF authenticates with `allauth.headless.contrib.rest_framework.authentication.JWTTokenAuthentication`.
- Clients use `/api/v1/auth/app/v1/...` (native, returns tokens). `/api/v1/auth/browser/v1/...` is available for
  session-cookie browser clients.
- Session auth is used only for the Django admin (and the staff-only Swagger/Redoc UIs). Admin sign-in goes
  through allauth's login (`secure_admin_login`) so the TOTP stage runs, and `has_permission` additionally
  requires staff to have MFA enabled (`ADMIN_REQUIRE_MFA`).
- allauth headless views are not DRF views, so per-IP throttles for login, signup, password reset and MFA are
  enforced by `api.v1.throttles.AuthEndpointThrottleMiddleware`.

## Consequences
- One token system instead of two; logout really revokes tokens.
- Refresh needs a database session lookup (stateful validation) - acceptable at our scale.
- A stable RSA key must be provisioned per environment; rotating it signs everyone out.
