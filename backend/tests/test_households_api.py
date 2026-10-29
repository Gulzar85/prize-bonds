import pytest
from django.urls import reverse

from apps.households.models import Household, Membership
from tests.factories import UserFactory

R = Membership.Role

DETAIL = "household-detail"
MEMBERS = "household-members"


def _url(name, household):  # type: ignore[no-untyped-def]
    return reverse(name, kwargs={"household_id": household.id})


@pytest.mark.django_db
class TestTenantIsolation:
    """User A must get 404 (never 403) for every endpoint of household B."""

    @pytest.mark.parametrize(
        ("name", "method", "body"),
        [(DETAIL, "get", None), (DETAIL, "patch", {"name": "x"}), (MEMBERS, "get", None)],
    )
    def test_non_member_gets_404(self, client_for, make_member, other_household, name, method, body):  # type: ignore[no-untyped-def]
        user_a = make_member(R.OWNER)  # owner of `household`, not of `other_household`
        client = client_for(user_a)
        response = getattr(client, method)(_url(name, other_household), body, format="json")
        assert response.status_code == 404

    def test_list_only_my_households(self, client_for, make_member, household, other_household):  # type: ignore[no-untyped-def]
        user = make_member(R.VIEWER)
        response = client_for(user).get(reverse("household-list"))
        assert response.status_code == 200
        ids = [h["id"] for h in response.data["results"]]
        assert ids == [str(household.id)]
        assert response.data["results"][0]["role"] == "VIEWER"

    def test_soft_deleted_household_is_404(self, client_for, make_member, household):  # type: ignore[no-untyped-def]
        user = make_member(R.OWNER)
        household.soft_delete()
        assert client_for(user).get(_url(DETAIL, household)).status_code == 404


# (endpoint name, method, body, expected status per actor)
MATRIX = [
    (DETAIL, "get", None, {R.OWNER: 200, R.EDITOR: 200, R.VIEWER: 200, "stranger": 404, "anon": 401}),
    (DETAIL, "patch", {"name": "Renamed"}, {R.OWNER: 200, R.EDITOR: 403, R.VIEWER: 403, "stranger": 404, "anon": 401}),
    (MEMBERS, "get", None, {R.OWNER: 200, R.EDITOR: 200, R.VIEWER: 200, "stranger": 404, "anon": 401}),
    (DETAIL, "delete", None, {R.OWNER: 405, R.EDITOR: 403, R.VIEWER: 403, "stranger": 404, "anon": 401}),
    (DETAIL, "put", {"name": "x"}, {R.OWNER: 405, R.EDITOR: 403, R.VIEWER: 403, "stranger": 404, "anon": 401}),
    (MEMBERS, "post", {}, {R.OWNER: 405, R.EDITOR: 403, R.VIEWER: 403, "stranger": 404, "anon": 401}),
]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "method", "body", "expected"),
    MATRIX,
    ids=[f"{m[1]}-{m[0]}" for m in MATRIX],
)
@pytest.mark.parametrize("actor", [R.OWNER, R.EDITOR, R.VIEWER, "stranger", "anon"])
def test_permission_matrix(client_for, make_member, household, name, method, body, expected, actor):  # type: ignore[no-untyped-def]
    if actor == "anon":
        user = None
    elif actor == "stranger":
        user = UserFactory()
    else:
        user = make_member(actor)
    response = getattr(client_for(user), method)(_url(name, household), body, format="json")
    assert response.status_code == expected[actor]


@pytest.mark.django_db
def test_list_requires_authentication(client_for):  # type: ignore[no-untyped-def]
    assert client_for(None).get(reverse("household-list")).status_code == 401


@pytest.mark.django_db
def test_rename_via_service(client_for, make_member, household):  # type: ignore[no-untyped-def]
    owner = make_member(R.OWNER)
    response = client_for(owner).patch(_url(DETAIL, household), {"name": "Family"}, format="json")
    assert response.status_code == 200
    assert response.data["name"] == "Family"
    assert response.data["role"] == "OWNER"
    assert Household.objects.get(pk=household.pk).name == "Family"


@pytest.mark.django_db
def test_rename_validation_is_problem_json(client_for, make_member, household):  # type: ignore[no-untyped-def]
    owner = make_member(R.OWNER)
    response = client_for(owner).patch(_url(DETAIL, household), {"name": ""}, format="json")
    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/problem+json")
    assert response.data["status"] == 400
    assert "errors" in response.data


@pytest.mark.django_db
def test_members_listing(client_for, make_member, household):  # type: ignore[no-untyped-def]
    make_member(R.OWNER)
    viewer = make_member(R.VIEWER)
    response = client_for(viewer).get(_url(MEMBERS, household))
    assert response.status_code == 200
    assert {m["role"] for m in response.data["results"]} == {"OWNER", "VIEWER"}


@pytest.mark.django_db
def test_members_query_count_is_constant(client_for, make_member, household, django_assert_max_num_queries):  # type: ignore[no-untyped-def]
    viewer = make_member(R.VIEWER)
    for _ in range(10):
        make_member(R.EDITOR)
    with django_assert_max_num_queries(8):
        assert client_for(viewer).get(_url(MEMBERS, household)).status_code == 200
