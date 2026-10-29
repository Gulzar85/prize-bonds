from django.urls import path

from apps.draws.api import views

urlpatterns = [
    path("denominations/", views.DenominationListView.as_view(), name="public-denominations"),
    path("draws/", views.DrawListView.as_view(), name="public-draw-list"),
    path("draws/<uuid:pk>/", views.DrawDetailView.as_view(), name="public-draw-detail"),
    path("draws/<uuid:pk>/numbers/", views.DrawNumbersView.as_view(), name="public-draw-numbers"),
    path("check/", views.CheckView.as_view(), name="public-check"),
]
