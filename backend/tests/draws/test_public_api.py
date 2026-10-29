import datetime

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.draws.api.views import CACHE_CONTROL, DISCLAIMER
from apps.draws.models import Draw, DrawRevision, PrizeTier, WinningNumber
from tests.draws.conftest import rs200
from tests.draws.factories import RevisionFactory, denomination

pytestmark = pytest.mark.django_db

BASE = "/api/v1/public"


def make_draw(
    slug="rs-200",
    date=datetime.date(2026, 9, 15),
    number=107,
    status=Draw.Status.PUBLISHED,
    revision_status=DrawRevision.Status.APPROVED,
    revision_no=1,
    first=("516806",),
    second=("381066", "425087"),
    third=("000133", "000215", "046388"),
    publish=True,
):
    """A draw with one revision, tiers and numbers written directly (fast, no parsing)."""
    from tests.draws.factories import DrawFactory

    draw = DrawFactory(denomination=denomination(slug), draw_date=date, draw_number=number, status=status)
    revision = RevisionFactory(
        draw=draw,
        revision_no=revision_no,
        status=revision_status,
        source_url=f"https://savings.gov.pk/wp-content/uploads/{date.year}/x-{number}.txt",
        reviewed_at=timezone.now() if revision_status == DrawRevision.Status.APPROVED else None,
    )
    for rank, amount, numbers in ((1, 750000, first), (2, 250000, second), (3, 1250, third)):
        tier = PrizeTier.objects.create(
            revision=revision, rank=rank, amount_pkr=amount, announced_count=len(numbers), parsed_count=len(numbers)
        )
        WinningNumber.objects.bulk_create(
            [
                WinningNumber(revision=revision, tier=tier, draw=draw, denomination=draw.denomination, number=n)
                for n in numbers
            ]
        )
    if publish:
        draw.published_revision = revision
        draw.published_at = timezone.now()
        draw.save(update_fields=["published_revision", "published_at"])
    return draw, revision


@pytest.fixture
def api():
    cache.clear()
    return APIClient()


def results(response):
    assert response.status_code == 200, response.content
    return response.json()["results"]


# --- published data only -----------------------------------------------------------------------------------------------


def test_only_published_draws_are_listed(api):
    published, _ = make_draw()
    make_draw(date=datetime.date(2026, 6, 15), number=106, status=Draw.Status.IN_REVIEW, publish=False)
    make_draw(date=datetime.date(2026, 3, 16), number=105, status=Draw.Status.FAILED, publish=False)
    make_draw(date=datetime.date(2025, 12, 15), number=104, status=Draw.Status.DISCOVERED, publish=False)
    assert [d["id"] for d in results(api.get(f"{BASE}/draws/"))] == [str(published.pk)]


@pytest.mark.parametrize("status", [Draw.Status.IN_REVIEW, Draw.Status.FAILED, Draw.Status.DISCOVERED])
def test_unpublished_draws_are_404_everywhere(api, status):
    draw, _ = make_draw(status=status, publish=False)
    assert api.get(f"{BASE}/draws/{draw.pk}/").status_code == 404
    assert api.get(f"{BASE}/draws/{draw.pk}/numbers/").status_code == 404


def test_numbers_of_unapproved_revisions_never_leak(api):
    draw, first_revision = make_draw()
    pending = RevisionFactory(draw=draw, revision_no=2, status=DrawRevision.Status.NEEDS_REVIEW)
    tier = PrizeTier.objects.create(revision=pending, rank=1, amount_pkr=1, announced_count=1, parsed_count=1)
    WinningNumber.objects.create(
        revision=pending, tier=tier, draw=draw, denomination=draw.denomination, number="999999"
    )
    body = api.get(f"{BASE}/draws/{draw.pk}/").json()
    assert body["tiers"][0]["numbers"] == ["516806"]  # the published revision, not the pending one
    listed = results(api.get(f"{BASE}/draws/{draw.pk}/numbers/?page_size=100"))
    assert "999999" not in {n["number"] for n in listed}
    check = api.post(f"{BASE}/check/", {"denomination": "rs-200", "numbers": ["999999"]}, format="json")
    assert check.json()["wins"] == []


def test_detail_has_header_tiers_dates_and_source(api):
    draw, _ = make_draw()
    body = api.get(f"{BASE}/draws/{draw.pk}/").json()
    assert body["draw_number"] == 107 and body["draw_date"] == "2026-09-15" and body["denomination"] == "rs-200"
    assert body["revised"] is False and body["revised_at"] is None
    assert body["published_at"]
    assert body["source_url"].startswith("https://savings.gov.pk/")
    tiers = {t["rank"]: t for t in body["tiers"]}
    assert tiers[1]["numbers"] == ["516806"] and tiers[1]["amount_pkr"] == 750000
    assert tiers[2]["numbers"] == ["381066", "425087"]
    assert tiers[3]["numbers"] is None and tiers[3]["count"] == 3  # the grid has its own endpoint
    assert body["disclaimer"] == DISCLAIMER


def test_a_revised_draw_reports_revised_and_serves_the_new_numbers(api):
    draw, _ = make_draw()
    revised = RevisionFactory(
        draw=draw, revision_no=2, status=DrawRevision.Status.APPROVED, reviewed_at=timezone.now(), source_url=""
    )
    tier = PrizeTier.objects.create(revision=revised, rank=1, amount_pkr=750000, announced_count=1, parsed_count=1)
    WinningNumber.objects.create(
        revision=revised, tier=tier, draw=draw, denomination=draw.denomination, number="516807"
    )
    draw.published_revision = revised
    draw.save(update_fields=["published_revision"])
    body = api.get(f"{BASE}/draws/{draw.pk}/").json()
    assert body["revised"] is True and body["revised_at"] is not None
    assert body["source_url"] is None  # a manual upload has no source URL
    assert body["tiers"][0]["numbers"] == ["516807"]


def test_denominations(api):
    body = api.get(f"{BASE}/denominations/").json()
    assert [d["slug"] for d in body["results"]] == [
        "rs-100",
        "rs-200",
        "rs-750",
        "rs-1500",
        "premium-25000",
        "premium-40000",
    ]
    assert body["disclaimer"] == DISCLAIMER
    rs200().__class__.objects.filter(slug="rs-100").update(is_active=False)
    assert "rs-100" not in [d["slug"] for d in api.get(f"{BASE}/denominations/").json()["results"]]


# --- filtering and pagination ----------------------------------------------------------------------------------------


def test_filters_by_denomination_and_year(api):
    make_draw(slug="rs-200", date=datetime.date(2026, 9, 15), number=107)
    make_draw(slug="rs-200", date=datetime.date(2025, 9, 15), number=103)
    make_draw(slug="rs-750", date=datetime.date(2026, 10, 15), number=108)
    assert {d["draw_number"] for d in results(api.get(f"{BASE}/draws/?denomination=rs-200"))} == {107, 103}
    assert {d["draw_number"] for d in results(api.get(f"{BASE}/draws/?year=2026"))} == {107, 108}
    assert [d["draw_number"] for d in results(api.get(f"{BASE}/draws/?denomination=rs-200&year=2025"))] == [103]
    assert results(api.get(f"{BASE}/draws/?denomination=nope")) == []


@pytest.mark.parametrize("year", ["abc", "1", "99999"])
def test_bad_year_is_a_400_problem(api, year):
    response = api.get(f"{BASE}/draws/?year={year}")
    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/problem+json")


def test_draw_list_is_cursor_paginated_newest_first(api):
    for index in range(5):
        make_draw(date=datetime.date(2026, 1, 1) + datetime.timedelta(days=index), number=100 + index)
    first = api.get(f"{BASE}/draws/?page_size=2").json()
    assert [d["draw_number"] for d in first["results"]] == [104, 103]
    assert "cursor=" in first["next"] and first["disclaimer"] == DISCLAIMER
    second = api.get(first["next"]).json()
    assert [d["draw_number"] for d in second["results"]] == [102, 101]


def test_numbers_are_paginated_and_filterable_by_tier(api):
    draw, _ = make_draw(third=tuple(f"{n:06d}" for n in range(1, 8)))
    page = api.get(f"{BASE}/draws/{draw.pk}/numbers/?tier=3&page_size=3").json()
    assert [n["number"] for n in page["results"]] == ["000001", "000002", "000003"]
    assert all(n["tier"] == 3 for n in page["results"])
    assert [n["number"] for n in api.get(page["next"]).json()["results"]] == ["000004", "000005", "000006"]
    assert [n["number"] for n in results(api.get(f"{BASE}/draws/{draw.pk}/numbers/?tier=1"))] == ["516806"]
    assert api.get(f"{BASE}/draws/{draw.pk}/numbers/?tier=9").status_code == 400


# --- check ------------------------------------------------------------------------------------------------------------


def check(api, **body):
    return api.post(f"{BASE}/check/", {"denomination": "rs-200", **body}, format="json")


def test_check_returns_every_win_across_draws_with_tier_and_amount(api):
    make_draw(date=datetime.date(2026, 9, 15), number=107)
    make_draw(date=datetime.date(2026, 6, 15), number=106, first=("111111",), second=("222222",), third=("516806",))
    body = check(api, numbers=["516806", "000001"]).json()
    wins = body["wins"]
    assert [(w["number"], w["draw_number"], w["tier"], w["amount_pkr"]) for w in wins] == [
        ("516806", 107, 1, 750000),
        ("516806", 106, 3, 1250),
    ]
    assert body["denomination"] == "rs-200" and body["disclaimer"] == DISCLAIMER


def test_check_ranges_and_numbers_together(api):
    make_draw()
    wins = check(api, numbers=["516806"], ranges=[{"from": "000100", "to": "000300"}]).json()["wins"]
    assert {w["number"] for w in wins} == {"516806", "000133", "000215"}


def test_check_is_scoped_to_the_denomination_and_to_published_draws(api):
    make_draw(slug="rs-750", number=108, date=datetime.date(2026, 10, 15))
    make_draw(status=Draw.Status.IN_REVIEW, publish=False, number=99, date=datetime.date(2026, 1, 1))
    assert check(api, numbers=["516806"]).json()["wins"] == []  # rs-200 has nothing published with that number
    other = api.post(f"{BASE}/check/", {"denomination": "rs-750", "numbers": ["516806"]}, format="json")
    assert len(other.json()["wins"]) == 1


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "non_field_errors"),
        ({"numbers": []}, "non_field_errors"),
        ({"numbers": ["12345"]}, "numbers"),  # too short
        ({"numbers": ["1234567"]}, "numbers"),  # too long
        ({"numbers": ["12345a"]}, "numbers"),
        ({"numbers": [f"{n:06d}" for n in range(51)]}, "numbers"),  # more than 50
        ({"ranges": [{"from": "000001", "to": "000002"}] * 6}, "ranges"),  # more than 5
        ({"ranges": [{"from": "000001", "to": "001001"}]}, "ranges"),  # 1,001 numbers
        ({"ranges": [{"from": "000010", "to": "000001"}]}, "ranges"),  # reversed
        ({"ranges": [{"from": "000001"}]}, "ranges"),
        ({"ranges": [{"from": "1", "to": "2"}]}, "ranges"),
        ({"ranges": [{"from": "000001", "to": "000002", "extra": "1"}]}, "ranges"),
    ],
)
def test_check_validates_strictly(api, body, field):
    response = check(api, **body)
    assert response.status_code == 400
    assert field in response.json()["errors"]


def test_check_accepts_the_documented_maximums(api):
    make_draw()
    numbers = [f"{n:06d}" for n in range(50)]
    ranges = [{"from": f"{i * 10_000:06d}", "to": f"{i * 10_000 + 999:06d}"} for i in range(5)]
    assert check(api, numbers=numbers, ranges=ranges).status_code == 200


def test_check_rejects_an_unknown_denomination_and_get(api):
    assert api.post(f"{BASE}/check/", {"denomination": "rs-5", "numbers": ["000001"]}, format="json").status_code == 400
    assert api.get(f"{BASE}/check/").status_code == 405


def test_check_is_read_only_and_ignores_credentials(api):
    from tests.factories import UserFactory

    make_draw()
    api.force_authenticate(UserFactory())
    assert check(api, numbers=["516806"]).status_code == 200
    assert Draw.objects.count() == 1


# --- headers ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/denominations/", "/draws/"])
def test_cache_headers_and_conditional_requests(api, path):
    make_draw()
    first = api.get(f"{BASE}{path}")
    assert first["Cache-Control"] == CACHE_CONTROL == "public, max-age=300"
    etag = first["ETag"]
    assert etag.startswith('"')
    again = api.get(f"{BASE}{path}", HTTP_IF_NONE_MATCH=etag)
    assert again.status_code == 304 and again.content == b""
    assert api.get(f"{BASE}{path}", HTTP_IF_NONE_MATCH='"stale"').status_code == 200


def test_etag_changes_when_the_data_changes(api):
    draw, _ = make_draw()
    before = api.get(f"{BASE}/draws/{draw.pk}/")["ETag"]
    Draw.objects.filter(pk=draw.pk).update(city="Quetta")
    assert api.get(f"{BASE}/draws/{draw.pk}/")["ETag"] != before


def test_detail_numbers_and_check_have_etags_too(api):
    draw, _ = make_draw()
    for response in (
        api.get(f"{BASE}/draws/{draw.pk}/"),
        api.get(f"{BASE}/draws/{draw.pk}/numbers/"),
        check(api, numbers=["516806"]),
    ):
        assert response["ETag"] and response["Cache-Control"] == CACHE_CONTROL


def test_every_public_response_carries_the_disclaimer(api):
    draw, _ = make_draw()
    for url in (
        f"{BASE}/denominations/",
        f"{BASE}/draws/",
        f"{BASE}/draws/{draw.pk}/",
        f"{BASE}/draws/{draw.pk}/numbers/",
    ):
        assert api.get(url).json()["disclaimer"] == DISCLAIMER
    assert check(api, numbers=["000001"]).json()["disclaimer"] == DISCLAIMER


def test_errors_are_not_cached(api):
    response = api.get(f"{BASE}/draws/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404
    assert "ETag" not in response and "max-age" not in response.get("Cache-Control", "")


# --- throttling --------------------------------------------------------------------------------------------------------


def test_anonymous_requests_are_throttled_per_ip_and_check_is_tighter(api, settings):
    from apps.draws.api import views

    rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "public": "3/minute", "public_check": "2/minute"}
    views.PublicThrottle.THROTTLE_RATES = rates
    views.CheckThrottle.THROTTLE_RATES = rates
    try:
        assert [api.get(f"{BASE}/denominations/").status_code for _ in range(4)] == [200, 200, 200, 429]
        cache.clear()
        assert [check(api, numbers=["000001"]).status_code for _ in range(3)] == [200, 200, 429]
        limited = check(api, numbers=["000001"])
        assert limited["Content-Type"].startswith("application/problem+json")
        assert "Retry-After" in limited
    finally:
        del views.PublicThrottle.THROTTLE_RATES
        del views.CheckThrottle.THROTTLE_RATES


def test_the_two_scopes_do_not_share_a_bucket(api):
    from apps.draws.api import views

    assert views.PublicThrottle.scope == "public" and views.CheckThrottle.scope == "public_check"


def test_public_endpoints_do_not_require_authentication_or_csrf(api):
    make_draw()
    csrf_client = APIClient(enforce_csrf_checks=True)
    assert (
        csrf_client.post(f"{BASE}/check/", {"denomination": "rs-200", "numbers": ["516806"]}, format="json").status_code
        == 200
    )


# --- constant query counts -------------------------------------------------------------------------------------------


def seed(count):
    for index in range(count):
        make_draw(date=datetime.date(2020, 1, 1) + datetime.timedelta(days=index), number=index + 1)


def count_queries(api, url, django_assert_max_num_queries, limit, method="get", body=None):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        response = api.post(url, body, format="json") if method == "post" else api.get(url)
    assert response.status_code == 200, response.content
    return len(queries)


@pytest.mark.parametrize("small,large", [(2, 12)])
def test_list_and_check_query_counts_do_not_grow_with_the_data(api, django_assert_max_num_queries, small, large):
    seed(small)
    list_small = count_queries(api, f"{BASE}/draws/?page_size=100", django_assert_max_num_queries, 10)
    body = {"denomination": "rs-200", "numbers": ["516806", "000133"]}
    check_small = count_queries(api, f"{BASE}/check/", django_assert_max_num_queries, 10, "post", body)
    seed_more = large - small
    for index in range(seed_more):
        make_draw(date=datetime.date(2021, 1, 1) + datetime.timedelta(days=index), number=1000 + index)
    list_large = count_queries(api, f"{BASE}/draws/?page_size=100", django_assert_max_num_queries, 10)
    check_large = count_queries(api, f"{BASE}/check/", django_assert_max_num_queries, 10, "post", body)
    assert list_large == list_small <= 3
    assert check_large == check_small <= 3


def test_detail_and_numbers_query_counts_are_constant(api, django_assert_max_num_queries):
    small, _ = make_draw(third=tuple(f"{n:06d}" for n in range(5)))
    big, _ = make_draw(
        date=datetime.date(2026, 6, 15),
        number=106,
        third=tuple(f"{n:06d}" for n in range(300)),
        second=("1" * 6, "2" * 6, "3" * 6),
    )
    detail = [count_queries(api, f"{BASE}/draws/{d.pk}/", django_assert_max_num_queries, 10) for d in (small, big)]
    numbers = [
        count_queries(api, f"{BASE}/draws/{d.pk}/numbers/", django_assert_max_num_queries, 10) for d in (small, big)
    ]
    assert detail[0] == detail[1] <= 5
    assert numbers[0] == numbers[1] <= 4


# --- documentation ------------------------------------------------------------------------------------------------------


def test_schema_documents_every_public_endpoint_with_examples(api):
    schema = api.get("/api/v1/schema/?format=json").json()
    paths = {p: v for p, v in schema["paths"].items() if p.startswith("/api/v1/public/")}
    assert set(paths) == {
        "/api/v1/public/denominations/",
        "/api/v1/public/draws/",
        "/api/v1/public/draws/{id}/",
        "/api/v1/public/draws/{id}/numbers/",
        "/api/v1/public/check/",
    }
    for path, operations in paths.items():
        for method, operation in operations.items():
            assert operation["summary"], (path, method)
            assert operation["tags"] == ["public"]
            content = operation["responses"]["200"]["content"]["application/json"]
            assert "example" in content or "examples" in content, (path, method)
    check_request = paths["/api/v1/public/check/"]["post"]["requestBody"]["content"]["application/json"]
    assert "examples" in check_request
