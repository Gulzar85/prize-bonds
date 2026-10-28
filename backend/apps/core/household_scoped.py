from django.db import models

from apps.core.managers import HouseholdScopedManager


class HouseholdScopedModel(models.Model):
    household = models.ForeignKey(
        "households.Household",
        on_delete=models.CASCADE,
        db_constraint=True,
    )

    objects = HouseholdScopedManager()

    class Meta:
        abstract = True
