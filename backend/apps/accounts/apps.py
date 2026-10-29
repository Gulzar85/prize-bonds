from django.apps import AppConfig
from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest


def _staff_with_mfa(request: HttpRequest) -> bool:
    from allauth.mfa.utils import is_mfa_enabled

    user = request.user
    if not (user.is_active and user.is_staff):
        return False
    return not settings.ADMIN_REQUIRE_MFA or is_mfa_enabled(user)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self) -> None:
        from allauth.account.decorators import secure_admin_login

        from apps.accounts import signals  # noqa: F401

        # Admin logins go through allauth so the TOTP stage runs; staff must also have MFA enabled.
        admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]
        admin.site.has_permission = _staff_with_mfa  # type: ignore[method-assign]
