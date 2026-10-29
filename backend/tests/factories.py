import factory
from allauth.account.models import EmailAddress
from factory.django import DjangoModelFactory

from apps.accounts.models import User
from apps.households.models import Household, Membership

PASSWORD = "Str0ng-Passw0rd!x"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")

    @factory.post_generation
    def password(self, create, extracted, **kwargs):  # type: ignore[no-untyped-def]
        self.set_password(extracted or PASSWORD)
        if create:
            self.save(update_fields=["password"])

    @factory.post_generation
    def verified(self, create, extracted, **kwargs):  # type: ignore[no-untyped-def]
        if create and extracted is not False:
            EmailAddress.objects.create(user=self, email=self.email, verified=True, primary=True)


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
