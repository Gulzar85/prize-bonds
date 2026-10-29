"""Django admin for the draw engine: the review queue, review screen and manual upload.

Everything is read-only except the review decision and the upload form; revisions are never edited or deleted.
Access requires the ``data_operator`` group *and* MFA (see :mod:`apps.draws.rules`).
"""

from typing import Any

from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html

from apps.draws.forms import ReviewDecisionForm, UploadRevisionForm
from apps.draws.models import Denomination, Draw, DrawRevision, DrawSchedule, IngestionRun, OutboxEvent
from apps.draws.rules import can_review, can_upload
from apps.draws.services import pipeline, review
from apps.draws.services.inspection import build_review_context
from apps.draws.states import IllegalTransition


class OperatorOnlyAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Visible to data operators only; read-only unless a subclass opens specific permissions."""

    def has_module_permission(self, request: HttpRequest) -> bool:
        return can_review(request.user)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return can_review(request.user)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Denomination)
class DenominationAdmin(OperatorOnlyAdmin):
    list_display = ("name_en", "value_pkr", "kind", "number_length", "is_active")


@admin.register(DrawSchedule)
class DrawScheduleAdmin(OperatorOnlyAdmin):
    """Scheduled draw dates (from NSS's yearly schedule) drive draw-day polling; operators maintain them."""

    list_display = ("denomination", "scheduled_date", "city")
    list_filter = ("denomination",)
    date_hierarchy = "scheduled_date"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return can_review(request.user)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return can_review(request.user)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return can_review(request.user)


@admin.register(Draw)
class DrawAdmin(OperatorOnlyAdmin):
    list_display = ("denomination", "draw_number", "draw_date", "city", "status", "published_at")
    list_filter = ("denomination", "status")
    date_hierarchy = "draw_date"


@admin.register(DrawRevision)
class DrawRevisionAdmin(OperatorOnlyAdmin):
    list_display = (
        "review_link",
        "draw",
        "revision_no",
        "status",
        "extraction_method",
        "errors",
        "warnings",
        "created_at",
    )
    list_display_links = None
    list_filter = ("status", "draw__denomination", "extraction_method")
    ordering = ("created_at",)  # oldest first: the queue is worked in order
    change_list_template = "admin/draws/revision_changelist.html"
    actions = ["approve_clean_backfill"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[DrawRevision]:
        queryset: QuerySet[DrawRevision] = super().get_queryset(request)
        return queryset.select_related("draw__denomination").annotate(tier_total=Count("tiers"))

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        # The queue is the default view: only revisions that need a decision.
        if not request.GET:
            return HttpResponseRedirect(f"{request.path}?status__exact={DrawRevision.Status.NEEDS_REVIEW}")
        return super().changelist_view(request, extra_context)

    @admin.display(description="Review")
    def review_link(self, obj: DrawRevision) -> str:
        url = reverse("admin:draws_drawrevision_review", args=[obj.pk])
        return format_html('<a href="{}">Open</a>', url)

    @admin.display(description="Errors")
    def errors(self, obj: DrawRevision) -> int:
        return len(obj.parse_errors)

    @admin.display(description="Warnings")
    def warnings(self, obj: DrawRevision) -> int:
        return len(obj.parse_warnings)

    @admin.action(description="Approve selected clean historical revisions (no findings)")
    def approve_clean_backfill(self, request: HttpRequest, queryset: QuerySet[DrawRevision]) -> None:
        try:
            result = review.bulk_approve_clean_backfill(request.user, queryset)  # type: ignore[arg-type]
        except review.ReviewError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return
        self.message_user(
            request,
            f"Approved {result.approved} clean revision(s); "
            f"{result.skipped} not eligible (findings, live, or not a first publication).",
            messages.SUCCESS,
        )

    def get_urls(self) -> list[URLPattern]:
        custom = [
            path("upload/", self.admin_site.admin_view(self.upload_view), name="draws_drawrevision_upload"),
            path(
                "<uuid:object_id>/review/",
                self.admin_site.admin_view(self.review_view),
                name="draws_drawrevision_review",
            ),
        ]
        return custom + super().get_urls()

    # -- review screen ----------------------------------------------------------------------------------------------

    def review_view(self, request: HttpRequest, object_id: Any) -> HttpResponse:
        if not can_review(request.user):
            return HttpResponse(status=403)
        revision = DrawRevision.objects.select_related("draw__denomination", "uploaded_by", "reviewed_by").get(
            pk=object_id
        )
        form = ReviewDecisionForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            decision = request.POST.get("decision")
            try:
                if decision == "approve":
                    review.approve_revision(
                        revision.pk,
                        request.user,  # type: ignore[arg-type]
                        form.cleaned_data["note"],
                        override_errors=form.cleaned_data["override_errors"],
                    )
                    self.message_user(request, "Revision approved and published.", messages.SUCCESS)
                elif decision == "reject":
                    review.reject_revision(revision.pk, request.user, form.cleaned_data["note"])  # type: ignore[arg-type]
                    self.message_user(request, "Revision rejected.", messages.WARNING)
                else:
                    form.add_error(None, "Choose Approve or Reject.")
                    return self._render_review(request, revision, form)
            except (review.ReviewError, IllegalTransition) as exc:
                self.message_user(request, str(exc), messages.ERROR)
                return self._render_review(request, revision, form)
            return HttpResponseRedirect(reverse("admin:draws_drawrevision_changelist"))
        return self._render_review(request, revision, form)

    def _render_review(self, request: HttpRequest, revision: DrawRevision, form: ReviewDecisionForm) -> HttpResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": f"Review {revision}",
            "review": build_review_context(revision),
            "form": form,
            "opts": self.model._meta,
            "four_eyes": settings.DRAWS_FOUR_EYES,
            "can_decide": revision.status == DrawRevision.Status.NEEDS_REVIEW,
        }
        return TemplateResponse(request, "admin/draws/revision_review.html", context)

    # -- manual upload ----------------------------------------------------------------------------------------------

    def upload_view(self, request: HttpRequest) -> HttpResponse:
        if not can_upload(request.user):
            return HttpResponse(status=403)
        form = UploadRevisionForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            upload = form.cleaned_data["file"]
            try:
                revision = pipeline.upload_revision(
                    form.cleaned_data["denomination"],
                    form.cleaned_data["draw_date"],
                    upload.read(),
                    upload.name or "",
                    request.user,  # type: ignore[arg-type]
                    settings.DRAWS_MAX_FILE_BYTES,
                )
            except pipeline.UploadRejected as exc:
                form.add_error("file", str(exc))
            else:
                self.message_user(request, "Uploaded and parsed. Another operator must approve it.", messages.SUCCESS)
                return HttpResponseRedirect(reverse("admin:draws_drawrevision_review", args=[revision.pk]))
        context = {
            **self.admin_site.each_context(request),
            "title": "Upload a draw result",
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/draws/revision_upload.html", context)


@admin.register(IngestionRun)
class IngestionRunAdmin(OperatorOnlyAdmin):
    list_display = (
        "trigger",
        "started_at",
        "finished_at",
        "outcome",
        "pages_fetched",
        "files_new",
        "files_unchanged",
        "files_failed",
    )
    list_filter = ("trigger", "outcome")


@admin.register(OutboxEvent)
class OutboxEventAdmin(OperatorOnlyAdmin):
    list_display = ("type", "created_at", "processed_at")
    list_filter = ("type",)
