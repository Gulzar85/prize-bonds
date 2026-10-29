from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils import translation

from apps.accounts.models import User


class AccountAdapter(DefaultAccountAdapter):  # type: ignore[misc]
    """Render account emails in the recipient's preferred language, not the request's."""

    def render_mail(
        self, template_prefix: str, email: str, context: dict[str, Any], headers: dict[str, str] | None = None
    ) -> EmailMessage | EmailMultiAlternatives:
        user = User.objects.filter(email__iexact=email).only("preferred_language").first()
        language = user.preferred_language if user else translation.get_language()
        with translation.override(language):
            return super().render_mail(template_prefix, email, context, headers)  # type: ignore[no-any-return]
