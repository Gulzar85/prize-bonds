from django.contrib.auth import get_user_model
from django.db import transaction

from apps.households.models import Household, Membership

User = get_user_model()


@transaction.atomic
def create_personal_household(user: User) -> Household:
    """Create a personal household for a user with OWNER role."""
    household = Household.objects.create(
        name=f"{user.get_full_name() or user.email}'s Household",
        created_by=user,
    )
    Membership.objects.create(
        user=user,
        household=household,
        role=Membership.Role.OWNER,
    )
    return household
