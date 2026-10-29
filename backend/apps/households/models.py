from django.conf import settings
from django.db import models

from apps.core.models import SoftDeleteModel, TimeStampedModel, UUIDModel


class Household(UUIDModel, TimeStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # DO_NOTHING keeps the database FK (NO ACTION == protect) while staying compatible
        # with the DB_CASCADE references to Household (Django forbids mixing Python and
        # database on_delete variants in one reference chain).
        on_delete=models.DO_NOTHING,
        related_name="created_households",
    )

    class Meta:
        db_table = "households_household"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["created_by"], name="household_creator_idx")]

    def __str__(self) -> str:
        return self.name


class Membership(UUIDModel, TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        EDITOR = "EDITOR", "Editor"
        VIEWER = "VIEWER", "Viewer"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="memberships")
    household = models.ForeignKey(Household, on_delete=models.DB_CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)

    class Meta:
        db_table = "households_membership"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "household"], name="membership_user_household_uniq"),
            models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "EDITOR", "VIEWER"]),
                name="valid_membership_role",
            ),
        ]
        indexes = [models.Index(fields=["household", "role"], name="membership_household_role_idx")]

    def __str__(self) -> str:
        return f"{self.user} - {self.household} ({self.role})"
