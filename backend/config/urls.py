from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from health_check.views import HealthCheckView
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAdminUser

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/v1/", include("api.v1.urls")),
    path("health/live/", HealthCheckView.as_view(checks=[]), name="health-live"),
    path(
        "health/ready/",
        HealthCheckView.as_view(checks=settings.HEALTH_READY_CHECKS),
        name="health-ready",
    ),
]

# Schema is public; the interactive UIs are for DEBUG or staff only.
ui_auth = [SessionAuthentication]  # staff browse the docs with their admin session
ui_permissions = [AllowAny] if settings.DEBUG else [IsAdminUser]
urlpatterns += [
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(
            url_name="schema", permission_classes=ui_permissions, authentication_classes=ui_auth
        ),
        name="swagger-ui",
    ),
    path(
        "api/v1/schema/redoc/",
        SpectacularRedocView.as_view(
            url_name="schema", permission_classes=ui_permissions, authentication_classes=ui_auth
        ),
        name="redoc",
    ),
]
