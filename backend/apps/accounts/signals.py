from typing import Any

from allauth.account.signals import email_confirmed
from django.dispatch import receiver

from apps.households.services import create_personal_household


@receiver(email_confirmed)
def on_email_confirmed(sender: Any, email_address: Any, **kwargs: Any) -> None:
    # No business logic here: the service decides what "first verified" means.
    create_personal_household(email_address.user)
