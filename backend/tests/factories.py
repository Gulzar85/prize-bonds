import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

from apps.households.models import Household, Membership

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    is_active = True


class HouseholdFactory(DjangoModelFactory):
    class Meta:
        model = Household

    name = factory.Sequence(lambda n: f"Household {n}")
    created_by = factory.SubFactory(UserFactory)


class MembershipFactory(DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    household = factory.SubFactory(HouseholdFactory)
    role = Membership.Role.OWNER
