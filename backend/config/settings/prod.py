from .base import *  # noqa

DEBUG = False

# Security settings for production
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# A real signing key is mandatory in production (no ephemeral fallback).
HEADLESS_JWT_PRIVATE_KEY = env("JWT_PRIVATE_KEY").replace(chr(92) + "n", chr(10))  # type: ignore

# CSP already defined in base for Django 6.1

# Sentry
SENTRY_DSN = env("SENTRY_DSN", default="")  # type: ignore
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment=env("SENTRY_ENVIRONMENT", default="production"),  # type: ignore
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

DRAWS_FOUR_EYES = env.bool("DRAWS_FOUR_EYES", default=True)  # type: ignore

# Raw draw files live in a private S3-compatible bucket (never public; pre-signed access only).
if env("DRAWS_S3_BUCKET", default=""):  # type: ignore
    STORAGES["draws_raw"] = {  # type: ignore
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("DRAWS_S3_BUCKET"),  # type: ignore
            "endpoint_url": env("DRAWS_S3_ENDPOINT_URL", default=None),  # type: ignore
            "access_key": env("DRAWS_S3_ACCESS_KEY", default=None),  # type: ignore
            "secret_key": env("DRAWS_S3_SECRET_KEY", default=None),  # type: ignore
            "default_acl": "private",
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }
