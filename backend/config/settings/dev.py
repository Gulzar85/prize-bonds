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

