from django.db import models


class HouseholdScopedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()

    def for_household(self, household):
        return self.get_queryset().filter(household=household)

    def visible_to(self, user):
        from apps.households.models import Membership

        household_ids = Membership.objects.filter(user=user).values_list(
            "household_id", flat=True
        )
        return self.get_queryset().filter(household_id__in=household_ids)
