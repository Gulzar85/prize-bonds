from .base import *  # noqa

DEBUG = True

SECRET_KEY = "test-secret-key"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

AXES_ENABLED = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Prize Bond Tracker API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
