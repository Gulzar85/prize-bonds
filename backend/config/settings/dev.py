from .base import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["django_extensions"]  # type: ignore

# CSP for development - more permissive for docs
SECURE_CSP = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'", "'unsafe-inline'", "'unsafe-eval'"),
        "style-src": ("'self'", "'unsafe-inline'"),
        "img-src": ("'self'", "data:", "blob:"),
        "font-src": ("'self'", "data:"),
        "connect-src": ("'self'",),
    }
}

# Email to console in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CORS allow all in dev
CORS_ALLOW_ALL_ORIGINS = True
