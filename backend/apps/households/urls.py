from django.urls import path

from apps.households import views

urlpatterns = [
    path("households/", views.HouseholdListView.as_view(), name="household-list"),
    path("households/<uuid:household_id>/", views.HouseholdDetailView.as_view(), name="household-detail"),
    path(
        "households/<uuid:household_id>/members/",
        views.HouseholdMembersView.as_view(),
        name="household-members",
    ),
]
