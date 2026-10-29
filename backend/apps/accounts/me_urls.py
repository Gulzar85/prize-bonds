from django.urls import path

from apps.accounts.views import MeView

urlpatterns = [path("", MeView.as_view(), name="me")]
