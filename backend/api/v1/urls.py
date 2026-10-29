from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.households.urls")),
    path("me/", include("apps.accounts.me_urls")),
    path("public/", include("apps.draws.urls")),
]
