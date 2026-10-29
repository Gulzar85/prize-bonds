from typing import ClassVar

from django.db import models

from apps.core.managers import HouseholdScopedManager


class HouseholdScopedModel(models.Model):
    """Base for every row owned by a household (tenant)."""

    household = models.ForeignKey(
        "households.Household",
        on_delete=models.DB_CASCADE,
        related_name="+",
    )

    objects: ClassVar[HouseholdScopedManager] = HouseholdScopedManager()

    class Meta:
        abstract = True
