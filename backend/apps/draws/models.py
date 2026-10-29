"""Draw engine data model.

Draw data is global (not household-scoped). Money is always an integer number of rupees.
Foreign keys from tiers and numbers to their revision use Django 6.1 ``DB_CASCADE``; every other
reference into the revision chain is ``DO_NOTHING`` (the database FK still refuses deletion), because
revisions and their numbers are never hard-deleted by application code.
"""

from typing import Any, ClassVar

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class Denomination(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        REGULAR = "REGULAR", "Regular"
        PREMIUM = "PREMIUM", "Premium"

    value_pkr = models.PositiveIntegerField(unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    slug = models.SlugField(unique=True)
    name_en = models.CharField(max_length=100)
    name_ur = models.CharField(max_length=100, blank=True)
    source_page_url = models.URLField()
    number_length = models.PositiveSmallIntegerField(default=6)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "value_pkr"]

    def __str__(self) -> str:
        return self.name_en


class DrawSchedule(UUIDModel, TimeStampedModel):
    """Admin-entered from NSS's yearly schedule; drives draw-day polling."""

    denomination = models.ForeignKey(Denomination, on_delete=models.CASCADE, related_name="schedules")
    scheduled_date = models.DateField()
    city = models.CharField(max_length=100, blank=True)
    #: Set when the "draw not found" alert was sent, so it fires once.
    missing_alerted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_date"]
        constraints = [
            models.UniqueConstraint(fields=["denomination", "scheduled_date"], name="schedule_denomination_date_uniq")
        ]

    def __str__(self) -> str:
        return f"{self.denomination} on {self.scheduled_date}"


class Draw(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        DISCOVERED = "DISCOVERED", "Discovered"
        IN_REVIEW = "IN_REVIEW", "In review"
        PUBLISHED = "PUBLISHED", "Published"
        FAILED = "FAILED", "Failed"

    denomination = models.ForeignKey(Denomination, on_delete=models.PROTECT, related_name="draws")
    draw_number = models.PositiveIntegerField(null=True, blank=True)
    draw_date = models.DateField()
    city = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DISCOVERED)
    published_revision = models.ForeignKey(
        "DrawRevision", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-draw_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["denomination", "draw_number"],
                condition=models.Q(draw_number__isnull=False),
                name="draw_denomination_number_uniq",
            ),
            models.UniqueConstraint(fields=["denomination", "draw_date"], name="draw_denomination_date_uniq"),
        ]
        indexes = [models.Index(fields=["status", "-draw_date"], name="draw_status_date_idx")]

    def __str__(self) -> str:
        return f"{self.denomination} #{self.draw_number or '?'} ({self.draw_date})"


class DrawRevision(UUIDModel, TimeStampedModel):
    """One fetched file for a draw. The source and parse fields are immutable once saved."""

    class Extraction(models.TextChoices):
        TXT = "TXT", "Text file"
        PDF_TEXT = "PDF_TEXT", "PDF text layer"
        DOC_CONVERT = "DOC_CONVERT", "DOC converted"
        DOCX = "DOCX", "DOCX"
        OCR = "OCR", "OCR"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PARSE_FAILED = "PARSE_FAILED", "Parse failed"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    #: Fields that may change after creation; everything else is frozen.
    MUTABLE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "diff_from_previous",
            "overdue_alerted_at",
            "extraction_method",
            "parsed_header",
            "parse_warnings",
            "parse_errors",
            "updated_at",
        }
    )

    draw = models.ForeignKey(Draw, on_delete=models.DO_NOTHING, related_name="revisions")
    revision_no = models.PositiveIntegerField()

    source_url = models.URLField(max_length=1000, blank=True)
    link_text = models.CharField(max_length=255, blank=True)
    file_ext = models.CharField(max_length=8)
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveIntegerField()
    storage_key = models.CharField(max_length=500)
    etag = models.CharField(max_length=255, blank=True)
    last_modified = models.CharField(max_length=100, blank=True)
    fetched_at = models.DateTimeField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.DO_NOTHING, related_name="+"
    )

    extraction_method = models.CharField(max_length=12, choices=Extraction.choices, blank=True)
    parsed_header = models.JSONField(default=dict, blank=True)
    parse_warnings = models.JSONField(default=list, blank=True)
    parse_errors = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=14, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.DO_NOTHING, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    diff_from_previous = models.JSONField(default=dict, blank=True)
    overdue_alerted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["draw_id", "-revision_no"]
        constraints = [
            models.UniqueConstraint(fields=["draw", "revision_no"], name="revision_draw_no_uniq"),
            models.UniqueConstraint(fields=["draw", "sha256"], name="revision_draw_sha_uniq"),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="revision_status_created_idx")]

    def __str__(self) -> str:
        return f"{self.draw} r{self.revision_no} [{self.status}]"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            if update_fields is None:
                raise ValueError("DrawRevision rows are immutable; save with update_fields of workflow fields only.")
            frozen = set(update_fields) - self.MUTABLE_FIELDS
            if frozen:
                raise ValueError(f"DrawRevision fields are immutable once saved: {sorted(frozen)}")
        super().save(*args, **kwargs)


class PrizeTier(UUIDModel, TimeStampedModel):
    revision = models.ForeignKey(DrawRevision, on_delete=models.DB_CASCADE, related_name="tiers")
    rank = models.PositiveSmallIntegerField()
    #: 0 means the file gave no usable amount; the validators report that as an error.
    amount_pkr = models.PositiveBigIntegerField()
    announced_count = models.PositiveIntegerField(null=True, blank=True)
    parsed_count = models.PositiveIntegerField()

    class Meta:
        ordering = ["revision_id", "rank"]
        constraints = [
            models.UniqueConstraint(fields=["revision", "rank"], name="tier_revision_rank_uniq"),
            models.CheckConstraint(condition=models.Q(rank__gte=1, rank__lte=3), name="tier_rank_1_to_3"),
        ]

    def __str__(self) -> str:
        return f"rank {self.rank}: Rs {self.amount_pkr}"


class WinningNumber(UUIDModel):
    revision = models.ForeignKey(DrawRevision, on_delete=models.DB_CASCADE, related_name="numbers")
    tier = models.ForeignKey(PrizeTier, on_delete=models.DB_CASCADE, related_name="numbers")
    # Denormalised for matching: Phase 2 looks numbers up by (denomination, number).
    draw = models.ForeignKey(Draw, on_delete=models.DO_NOTHING, related_name="+")
    denomination = models.ForeignKey(Denomination, on_delete=models.DO_NOTHING, related_name="+")
    number = models.CharField(max_length=10)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["revision", "number"], name="number_revision_uniq")]
        indexes = [
            models.Index(fields=["denomination", "number"], name="number_denomination_idx"),
            models.Index(fields=["draw", "tier"], name="number_draw_tier_idx"),
        ]

    def __str__(self) -> str:
        return self.number


class IngestionRun(UUIDModel):
    class Trigger(models.TextChoices):
        SCHEDULE = "SCHEDULE", "Schedule"
        DRAW_DAY = "DRAW_DAY", "Draw day"
        BACKFILL = "BACKFILL", "Backfill"
        MANUAL = "MANUAL", "Manual"

    class Outcome(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        PARTIAL = "PARTIAL", "Partial"
        FAILED = "FAILED", "Failed"

    trigger = models.CharField(max_length=10, choices=Trigger.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.RUNNING)
    pages_fetched = models.PositiveIntegerField(default=0)
    files_new = models.PositiveIntegerField(default=0)
    files_unchanged = models.PositiveIntegerField(default=0)
    files_failed = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.trigger} {self.started_at:%Y-%m-%d %H:%M} {self.outcome}"


class OutboxEvent(UUIDModel):
    """Transactional outbox: written in the same transaction as the state change it describes."""

    class Type(models.TextChoices):
        PUBLISHED = "draw.published", "Draw published"
        REVISED = "draw.revised", "Draw revised"

    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["processed_at", "created_at"], name="outbox_unprocessed_idx")]

    def __str__(self) -> str:
        return f"{self.type} {self.created_at:%Y-%m-%d %H:%M}"
