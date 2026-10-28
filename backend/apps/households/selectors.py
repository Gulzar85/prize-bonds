from django.contrib.auth import get_user_model

from apps.households.models import Household, Membership

User = get_user_model()


def get_user_households(user: User):
    return Household.objects.filter(
        memberships__user=user,
        deleted_at__isnull=True,
    ).distinct()


def get_user_membership(user: User, household: Household):
    return Membership.objects.filter(user=user, household=household).first()
