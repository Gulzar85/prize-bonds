import hashlib
from pathlib import Path

import httpx
import pytest
import respx

from apps.draws.ingestion.fetcher import (
    Fetched,
    Fetcher,
    FetcherConfig,
    FetchFailed,
    FileTooLarge,
    HostNotAllowed,
    NotModified,
    RobotsDisallowed,
    UnexpectedContentType,
    build_ssl_context,
)

ROBOTS = (Path(__file__).resolve().parent.parent / "fixtures" / "draws_html" / "robots.txt").read_text(encoding="utf-8")
FILE_URL = "https://savings.gov.pk/wp-content/uploads/2026/09/200_150926.txt"
CONFIG = FetcherConfig(
    user_agent="Test/1.0 (+mailto:ops@example.com)",
    allowed_hosts=("savings.gov.pk", "www.savings.gov.pk"),
    min_interval=2.0,
    max_bytes=1000,
    backoff_base=1.0,
)


class Clock:
    """Fake time: sleeping advances the clock, so rate limiting is testable without waiting."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://savings.gov.pk/robots.txt").respond(200, text=ROBOTS)
        yield mock


def make(clock, **overrides) -> Fetcher:
    config = FetcherConfig(**{**CONFIG.__dict__, **overrides})
    return Fetcher(
        config, client=httpx.Client(headers={"User-Agent": config.user_agent}), sleep=clock.sleep, clock=clock
    )


def txt(body: bytes = b"107th DRAW", **headers):
    return httpx.Response(200, content=body, headers={"content-type": "text/plain; charset=utf-8", **headers})


def test_downloads_and_hashes_a_file(router, clock):
    router.get(FILE_URL).mock(
        return_value=txt(b"hello", etag='"abc"', **{"last-modified": "Tue, 15 Sep 2026 10:00:00 GMT"})
    )
    result = make(clock).get_file(FILE_URL, "txt")
    assert isinstance(result, Fetched)
    assert result.content == b"hello"
    assert result.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert result.etag == '"abc"'
    assert result.last_modified == "Tue, 15 Sep 2026 10:00:00 GMT"
    assert result.content_type == "text/plain"


def test_sends_the_descriptive_user_agent(router, clock):
    route = router.get(FILE_URL).mock(return_value=txt())
    make(clock).get_file(FILE_URL, "txt")
    assert route.calls.last.request.headers["user-agent"] == "Test/1.0 (+mailto:ops@example.com)"


def test_conditional_get_sends_validators_and_304_is_a_no_op(router, clock):
    route = router.get(FILE_URL).mock(return_value=httpx.Response(304))
    result = make(clock).get_file(FILE_URL, "txt", etag='"abc"', last_modified="Tue, 15 Sep 2026 10:00:00 GMT")
    assert isinstance(result, NotModified)
    sent = route.calls.last.request.headers
    assert sent["if-none-match"] == '"abc"'
    assert sent["if-modified-since"] == "Tue, 15 Sep 2026 10:00:00 GMT"


def test_no_validators_means_no_conditional_headers(router, clock):
    route = router.get(FILE_URL).mock(return_value=txt())
    make(clock).get_file(FILE_URL, "txt")
    assert "if-none-match" not in route.calls.last.request.headers


# --- safety -----------------------------------------------------------------------------------------------------------


def test_off_host_url_is_refused_before_any_request(router, clock):
    with pytest.raises(HostNotAllowed):
        make(clock).get_file("https://evil.example.com/x.txt", "txt")
    assert router.calls.call_count == 0


def test_plain_http_is_refused(router, clock):
    with pytest.raises(HostNotAllowed, match="https"):
        make(clock).get_file("http://savings.gov.pk/x.txt", "txt")


def test_redirect_to_another_host_is_rejected(router, clock):
    router.get(FILE_URL).respond(302, headers={"location": "https://evil.example.com/steal.txt"})
    with pytest.raises(HostNotAllowed):
        make(clock).get_file(FILE_URL, "txt")
    assert not any(c.request.url.host == "evil.example.com" for c in router.calls)


def test_redirect_within_the_allow_list_is_followed(router, clock):
    router.get(FILE_URL).respond(301, headers={"location": "https://www.savings.gov.pk/new.txt"})
    router.get("https://www.savings.gov.pk/robots.txt").respond(200, text=ROBOTS)
    router.get("https://www.savings.gov.pk/new.txt").mock(return_value=txt(b"moved"))
    result = make(clock).get_file(FILE_URL, "txt")
    assert result.content == b"moved"
    assert result.url == "https://www.savings.gov.pk/new.txt"


def test_redirect_loop_is_cut_off(router, clock):
    router.get(FILE_URL).respond(302, headers={"location": FILE_URL})
    with pytest.raises(FetchFailed, match="redirects"):
        make(clock).get_file(FILE_URL, "txt")


def test_redirect_without_location_fails(router, clock):
    router.get(FILE_URL).respond(302)
    with pytest.raises(FetchFailed, match="Location"):
        make(clock).get_file(FILE_URL, "txt")


def test_declared_oversize_is_rejected(router, clock):
    router.get(FILE_URL).mock(return_value=txt(b"x" * 10, **{"content-length": "999999"}))
    with pytest.raises(FileTooLarge):
        make(clock).get_file(FILE_URL, "txt")


def test_undeclared_oversize_is_rejected_while_streaming(router, clock):
    router.get(FILE_URL).mock(
        return_value=httpx.Response(200, content=b"x" * 2000, headers={"content-type": "text/plain"})
    )
    with pytest.raises(FileTooLarge, match="exceeds"):
        make(clock).get_file(FILE_URL, "txt")


@pytest.mark.parametrize(
    ("ext", "content_type"),
    [("txt", "text/html"), ("txt", "application/pdf"), ("pdf", "text/plain"), ("docx", "application/msword")],
)
def test_content_type_must_match_the_extension(router, clock, ext, content_type):
    url = FILE_URL.replace(".txt", f".{ext}")
    router.get(url).mock(return_value=httpx.Response(200, content=b"x", headers={"content-type": content_type}))
    with pytest.raises(UnexpectedContentType):
        make(clock).get_file(url, ext)


def test_unsupported_extension_is_refused(router, clock):
    url = FILE_URL.replace(".txt", ".exe")
    router.get(url).mock(return_value=httpx.Response(200, content=b"x", headers={"content-type": "text/plain"}))
    with pytest.raises(UnexpectedContentType, match="Unsupported"):
        make(clock).get_file(url, "exe")


def test_parameters_on_the_content_type_are_ignored(router, clock):
    router.get(FILE_URL).mock(
        return_value=httpx.Response(200, content=b"ok", headers={"content-type": "Text/Plain; charset=UTF-8"})
    )
    assert make(clock).get_file(FILE_URL, "txt").content == b"ok"


def test_robots_txt_is_respected(clock):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://savings.gov.pk/robots.txt").respond(200, text="User-agent: *\nDisallow: /wp-content/")
        route = mock.get(FILE_URL).mock(return_value=txt())
        with pytest.raises(RobotsDisallowed):
            make(clock).get_file(FILE_URL, "txt")
        assert not route.called


def test_robots_txt_is_fetched_once_and_cached(router, clock):
    router.get(FILE_URL).mock(return_value=txt())
    fetcher = make(clock)
    fetcher.get_file(FILE_URL, "txt")
    fetcher.get_file(FILE_URL, "txt")
    assert sum(1 for c in router.calls if c.request.url.path == "/robots.txt") == 1


def test_missing_robots_txt_means_allowed(clock):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://savings.gov.pk/robots.txt").respond(404)
        mock.get(FILE_URL).mock(return_value=txt(b"fine"))
        assert make(clock).get_file(FILE_URL, "txt").content == b"fine"


# --- politeness and resilience -----------------------------------------------------------------------------------------


def test_requests_are_spaced_by_the_minimum_interval(router, clock):
    router.get(FILE_URL).mock(return_value=txt())
    fetcher = make(clock)
    fetcher.get_file(FILE_URL, "txt")
    fetcher.get_file(FILE_URL, "txt")
    assert clock.sleeps  # the second request had to wait
    assert all(1.99 <= s <= 2.0 for s in clock.sleeps)


def test_429_backs_off_exponentially_then_succeeds(router, clock):
    route = router.get(FILE_URL)
    route.side_effect = [httpx.Response(429), httpx.Response(503), txt(b"finally")]
    result = make(clock).get_file(FILE_URL, "txt")
    assert result.content == b"finally"
    assert route.call_count == 3
    assert [s for s in clock.sleeps if s >= 1.0 and s != 2.0][:2] == [1.0, 2.0] or {1.0, 2.0} <= set(clock.sleeps)


def test_persistent_server_error_gives_up(router, clock):
    route = router.get(FILE_URL).respond(500)
    with pytest.raises(FetchFailed, match="giving up"):
        make(clock, max_retries=2).get_file(FILE_URL, "txt")
    assert route.call_count == 3


def test_transport_errors_are_retried(router, clock):
    route = router.get(FILE_URL)
    route.side_effect = [httpx.ConnectError("boom"), txt(b"recovered")]
    assert make(clock).get_file(FILE_URL, "txt").content == b"recovered"


def test_404_is_a_failure_not_a_retry(router, clock):
    route = router.get(FILE_URL).respond(404)
    with pytest.raises(FetchFailed, match="404"):
        make(clock).get_file(FILE_URL, "txt")
    assert route.call_count == 1


# --- pages --------------------------------------------------------------------------------------------------------------


def test_get_page_returns_html_text(router, clock):
    url = "https://savings.gov.pk/rs-200-prize-bond-draw/"
    router.get(url).mock(
        return_value=httpx.Response(200, text="<h2>2026</h2>", headers={"content-type": "text/html; charset=UTF-8"})
    )
    assert make(clock).get_page(url) == "<h2>2026</h2>"


def test_get_page_rejects_non_html_and_errors(router, clock):
    url = "https://savings.gov.pk/rs-200-prize-bond-draw/"
    router.get(url).mock(return_value=httpx.Response(200, text="x", headers={"content-type": "application/json"}))
    with pytest.raises(UnexpectedContentType):
        make(clock).get_page(url)
    router.get(url).respond(500)
    with pytest.raises(FetchFailed):
        make(clock, max_retries=0).get_page(url)
    router.get(url).respond(403)
    with pytest.raises(FetchFailed, match="403"):
        make(clock).get_page(url)


# --- TLS ----------------------------------------------------------------------------------------------------------------


def test_ssl_context_trusts_the_pinned_intermediate_and_still_verifies():
    context = build_ssl_context()
    assert context.verify_mode.name == "CERT_REQUIRED"
    assert context.check_hostname is True
    subjects = [dict(x[0] for x in cert["subject"]) for cert in context.get_ca_certs()]
    assert any(s.get("commonName") == "GoGetSSL RSA DV SSL CA 2" for s in subjects)


def test_default_client_is_built_with_that_context():
    fetcher = Fetcher(CONFIG)
    try:
        assert fetcher.client is not None
        assert str(fetcher.client.headers["user-agent"]).startswith("Test/1.0")
    finally:
        fetcher.close()
