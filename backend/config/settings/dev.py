from .base import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ["*"]

# CSP for development - more permissive for docs
from django.utils.csp import CSP

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.UNSAFE_INLINE, CSP.UNSAFE_EVAL],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:", "blob:"],
    "font-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
}

# Email to console in dev
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

# CORS allow all in dev
CORS_ALLOW_ALL_ORIGINS = True

# Use local cache in dev without Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery eager in dev
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True


STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Ephemeral signing key unless JWT_PRIVATE_KEY is set: dev tokens stop working after a restart.
if not HEADLESS_JWT_PRIVATE_KEY:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    HEADLESS_JWT_PRIVATE_KEY = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        .decode()
    )
