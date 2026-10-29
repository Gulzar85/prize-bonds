from django.conf import settings
from django.db import models

from apps.core.models import SoftDeleteModel, TimeStampedModel, UUIDModel


class Household(UUIDModel, TimeStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_households",
    )

    class Meta:
        db_table = "households_household"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Membership(UUIDModel, TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        EDITOR = "EDITOR", "Editor"
        VIEWER = "VIEWER", "Viewer"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)

    class Meta:
        db_table = "households_membership"
        unique_together = [["user", "household"]]
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "EDITOR", "VIEWER"]),
                name="valid_membership_role",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.household.name} ({self.role})"
