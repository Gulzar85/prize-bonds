import uuid
from typing import ClassVar

from django.db import models
from django.utils import timezone

from apps.core.managers import FetchPeersManager, SoftDeleteManager


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects: ClassVar[SoftDeleteManager] = SoftDeleteManager()
    all_objects: ClassVar[FetchPeersManager] = FetchPeersManager()

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])
