import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_user_cannot_access_other_household_detail(authenticated_client, other_household):
    url = reverse("household-detail", kwargs={"pk": other_household.id})
    response = authenticated_client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_user_cannot_access_other_household_members(authenticated_client, other_household):
    url = reverse("household-members", kwargs={"pk": other_household.id})
    response = authenticated_client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_user_can_only_see_own_households(authenticated_client, household, other_household):
    url = reverse("household-list")
    response = authenticated_client.get(url)
    assert response.status_code == 200
    household_ids = [h["id"] for h in response.data]
    assert str(household.id) in household_ids
    assert str(other_household.id) not in household_ids
