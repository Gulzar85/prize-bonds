from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from health_check.views import HealthCheckView

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

# Only serve docs in DEBUG or for staff
if settings.DEBUG:
    urlpatterns += [
        path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/v1/schema/swagger-ui/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/v1/schema/redoc/",
            SpectacularRedocView.as_view(url_name="redoc"),
            name="redoc",
        ),
    ]
else:
    # In production, still allow staff to access docs
    urlpatterns += [
        path("api/v1/schema/", SpectacularAPIView.as_view(permission_classes=[]), name="schema"),
        path(
            "api/v1/schema/swagger-ui/",
            SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[]),
            name="swagger-ui",
        ),
        path(
            "api/v1/schema/redoc/",
            SpectacularRedocView.as_view(url_name="redoc", permission_classes=[]),
            name="redoc",
        ),
    ]
