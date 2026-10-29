from django.apps import AppConfig


class DrawsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.draws"
    verbose_name = "Draws"

    def ready(self) -> None:
        from auditlog.registry import auditlog

        from apps.draws import rules  # noqa: F401
        from apps.draws.models import Draw, DrawRevision

        # Every status change, approval and override is audit-logged.
        auditlog.register(Draw)
        auditlog.register(
            DrawRevision, exclude_fields=["parsed_header", "parse_warnings", "parse_errors", "diff_from_previous"]
        )
