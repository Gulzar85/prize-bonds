from django.urls import include, path

urlpatterns = [
    # allauth headless: /auth/app/v1/... (JWT) and /auth/browser/v1/... (session)
    path("", include("allauth.headless.urls")),
]
