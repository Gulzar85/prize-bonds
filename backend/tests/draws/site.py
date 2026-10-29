"""A fake savings.gov.pk built from recorded pages and downloaded fixture files, served through respx."""

import json
import re
from pathlib import Path

import httpx
import respx

from apps.draws.ingestion.fetcher import Fetcher, FetcherConfig

TESTS = Path(__file__).resolve().parent.parent
HTML = TESTS / "fixtures" / "draws_html"
MANIFEST = json.loads((TESTS / "fixtures" / "draws" / "manifest.json").read_text(encoding="utf-8"))["fixtures"]
CONTENT_TYPES = {
    "txt": "text/plain",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
BASE = "https://savings.gov.pk"
PAGE_SLUGS = {
    "rs-100": "rs-100-prize-bond-draw",
    "rs-200": "rs-200-prize-bond-draw",
    "rs-750": "rs-750-prize-bond-draw",
    "rs-1500": "rs-1500-prize-bond-draw",
    "premium-25000": "premium-prize-bond-rs-25000",
    "premium-40000": "premium-prize-bond-rs-40000",
}


class Clock:
    """Fake time so rate limiting and backoff cost nothing."""

    def __init__(self) -> None:
        self.now = 1000.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


class FakeSite:
    def __init__(self, router: respx.MockRouter) -> None:
        self.router = router
        self.pages = {slug: (HTML / f"{path}.html").read_text(encoding="utf-8") for slug, path in PAGE_SLUGS.items()}
        self.original_pages = dict(self.pages)
        self.index = (HTML / "index.html").read_text(encoding="utf-8")
        self.files = {entry["source_url"]: (TESTS.parent / entry["file"]).read_bytes() for entry in MANIFEST}
        self.unavailable: set[str] = set()
        self.request_log: list[str] = []
        router.route(host="savings.gov.pk").mock(side_effect=self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.request_log.append(url)
        if url in self.unavailable:
            return httpx.Response(503)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=(HTML / "robots.txt").read_text(encoding="utf-8"))
        if url.rstrip("/") == f"{BASE}/download-draws":
            return httpx.Response(200, text=self.index, headers={"content-type": "text/html; charset=UTF-8"})
        for slug, path in PAGE_SLUGS.items():
            if url.rstrip("/") == f"{BASE}/{path}":
                return httpx.Response(200, text=self.pages[slug], headers={"content-type": "text/html; charset=UTF-8"})
        if url in self.files:
            ext = url.rsplit(".", 1)[-1].lower()
            return httpx.Response(200, content=self.files[url], headers={"content-type": CONTENT_TYPES[ext]})
        return httpx.Response(404)

    def requests_for(self, fragment: str) -> int:
        return sum(1 for u in self.request_log if fragment in u)

    def drop_link(self, slug: str, url_fragment: str) -> None:
        """Remove the <h2> that holds a link, as if the file had not been published yet."""
        html = self.pages[slug]
        pattern = re.compile(r"<h2[^>]*>(?:(?!</h2>).)*" + re.escape(url_fragment) + r"(?:(?!</h2>).)*</h2>", re.S)
        stripped, count = pattern.subn("", html)
        assert count == 1, f"expected to remove exactly one heading, removed {count}"
        self.pages[slug] = stripped


def make_fetcher(clock: Clock) -> Fetcher:
    config = FetcherConfig(
        user_agent="Test/1.0 (+mailto:ops@example.com)",
        allowed_hosts=("savings.gov.pk", "www.savings.gov.pk"),
        min_interval=2.0,
        max_bytes=20 * 1024 * 1024,
        backoff_base=0.0,
        max_retries=1,
    )
    return Fetcher(
        config, client=httpx.Client(headers={"User-Agent": config.user_agent}), sleep=clock.sleep, clock=clock
    )
