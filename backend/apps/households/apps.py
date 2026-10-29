from django.apps import AppConfig


class HouseholdsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.households"
    verbose_name = "Households"

    def ready(self) -> None:
        from apps.households import audit, rules  # noqa: F401
