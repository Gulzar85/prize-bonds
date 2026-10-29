from .base import *  # noqa

DEBUG = True

SECRET_KEY = "test-secret-key"
ALLOWED_HOSTS = ["*"]

# CI sets DATABASE_URL to real Postgres; local runs fall back to in-memory SQLite.
DATABASES = {"default": env.db("DATABASE_URL", default="sqlite:///:memory:")}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

AXES_ENABLED = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Keep health checks but they may fail in test env without services

SPECTACULAR_SETTINGS = {
    "TITLE": "Prize Bond Tracker API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# No broker or worker in the test process.
HEALTH_READY_CHECKS = ["health_check.checks.Database", "health_check.checks.Cache"]

ADMIN_REQUIRE_MFA = True
AUTH_THROTTLE_RATES = {
    "login": "1000/minute",
    "signup": "1000/minute",
    "password_reset": "1000/minute",
    "mfa": "1000/minute",
}
ACCOUNT_RATE_LIMITS = False
AXES_ENABLED = False

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

HEADLESS_JWT_PRIVATE_KEY = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    .decode()
)

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
