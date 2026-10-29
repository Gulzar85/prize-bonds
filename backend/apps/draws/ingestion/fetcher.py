"""Polite, safe downloads from savings.gov.pk. No Django imports; settings arrive through :class:`FetcherConfig`.

Rules enforced here: host allow-list re-checked on every redirect (SSRF guard), robots.txt, at most one request per
``min_interval`` seconds, exponential backoff on 429/5xx and transport errors, a size cap while streaming, content type
checked against the file extension, conditional GET with ETag / Last-Modified, and TLS verified against certifi plus the
pinned intermediate certificate the site fails to send.
"""

import hashlib
import ssl
import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import certifi
import httpx

CERTS_DIR = Path(__file__).resolve().parent / "certs"
#: The site sends the wrong intermediates (it omits "GoGetSSL RSA DV SSL CA 2"), so OpenSSL cannot build the chain.
PINNED_INTERMEDIATES = (CERTS_DIR / "gogetssl-rsa-dv-ssl-ca-2.pem",)

MAX_REDIRECTS = 5
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

#: extension -> acceptable Content-Type values (parameters such as charset are ignored)
EXPECTED_CONTENT_TYPES: dict[str, frozenset[str]] = {
    "txt": frozenset({"text/plain"}),
    "pdf": frozenset({"application/pdf"}),
    "doc": frozenset({"application/msword"}),
    "docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    "html": frozenset({"text/html"}),
}


class FetchError(Exception):
    """Base class: the fetch failed and nothing should be stored."""


class HostNotAllowed(FetchError):
    pass


class RobotsDisallowed(FetchError):
    pass


class FileTooLarge(FetchError):
    pass


class UnexpectedContentType(FetchError):
    pass


class FetchFailed(FetchError):
    """Retries exhausted or an unusable status code."""


@dataclass(frozen=True)
class FetcherConfig:
    user_agent: str
    allowed_hosts: tuple[str, ...]
    min_interval: float = 2.0
    max_bytes: int = 20 * 1024 * 1024
    max_retries: int = 4
    backoff_base: float = 1.0
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    verify_robots: bool = True


@dataclass(frozen=True)
class Fetched:
    url: str  # final URL after redirects
    content: bytes
    sha256: str
    content_type: str
    etag: str
    last_modified: str


@dataclass(frozen=True)
class NotModified:
    url: str


def build_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    for certificate in PINNED_INTERMEDIATES:
        context.load_verify_locations(cafile=str(certificate))
    # A pinned intermediate is a trust anchor even though it is not self-signed.
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context


@dataclass
class Fetcher:
    config: FetcherConfig
    client: httpx.Client | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _last_request: float | None = field(default=None, init=False)
    _robots: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(
                headers={"User-Agent": self.config.user_agent},
                timeout=httpx.Timeout(self.config.read_timeout, connect=self.config.connect_timeout),
                verify=build_ssl_context(),
                follow_redirects=False,
            )

    def close(self) -> None:
        if self.client is not None:
            self.client.close()

    # -- guards ------------------------------------------------------------

    def _check_host(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise HostNotAllowed(f"Only https is allowed: {url}")
        if parsed.hostname not in self.config.allowed_hosts:
            raise HostNotAllowed(f"Host not allowed: {parsed.hostname}")

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self.config.min_interval - (self.clock() - self._last_request)
            if wait > 0:
                self.sleep(wait)
        self._last_request = self.clock()

    def _check_robots(self, url: str) -> None:
        if not self.config.verify_robots:
            return
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            robots = urllib.robotparser.RobotFileParser()
            lines: list[str] = []
            try:
                response = self._request("GET", f"{origin}/robots.txt", check_robots=False)
                if response.status_code == 200:
                    lines = response.text.splitlines()
                    robots.parse(lines)
                else:
                    robots.parse([])  # no usable robots.txt: everything allowed
            except FetchError:
                robots.parse([])
            self._robots[origin] = robots
        if not self._robots[origin].can_fetch(self.config.user_agent, url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

    # -- requests ------------------------------------------------------------

    def _request(
        self, method: str, url: str, headers: dict[str, str] | None = None, check_robots: bool = True
    ) -> httpx.Response:
        """One logical request: allow-list, robots, throttle, manual redirects (re-checked), retry with backoff."""
        assert self.client is not None
        current = url
        for _hop in range(MAX_REDIRECTS + 1):
            self._check_host(current)
            if check_robots:
                self._check_robots(current)
            response = self._send_with_retries(method, current, headers or {})
            if response.is_redirect and response.status_code != 304:
                location = response.headers.get("location")
                if not location:
                    raise FetchFailed(f"Redirect without Location from {current}")
                current = urljoin(current, location)
                continue
            return response
        raise FetchFailed(f"Too many redirects from {url}")

    def _send_with_retries(self, method: str, url: str, headers: dict[str, str]) -> httpx.Response:
        assert self.client is not None
        last_problem = ""
        for attempt in range(self.config.max_retries + 1):
            self._throttle()
            try:
                with self.client.stream(method, url, headers=headers) as response:
                    if response.status_code in RETRY_STATUSES:
                        last_problem = f"HTTP {response.status_code}"
                    else:
                        return self._read_capped(response)
            except httpx.TransportError as exc:
                last_problem = type(exc).__name__
            self.sleep(self.config.backoff_base * 2**attempt)
        raise FetchFailed(f"{url}: giving up after {self.config.max_retries + 1} attempts ({last_problem})")

    def _read_capped(self, response: httpx.Response) -> httpx.Response:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.config.max_bytes:
            raise FileTooLarge(f"Declared size {declared} exceeds {self.config.max_bytes}")
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > self.config.max_bytes:
                raise FileTooLarge(f"Download exceeds {self.config.max_bytes} bytes")
        # Rebuild a fully read response so callers can use .content after the stream is closed. The body is already
        # decoded, so the encoding headers must go or httpx would decompress it a second time (the site gzips .txt).
        headers = [
            (k, v)
            for k, v in response.headers.multi_items()
            if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
        ]
        return httpx.Response(response.status_code, headers=headers, content=bytes(body), request=response.request)

    # -- public API ------------------------------------------------------------

    def get_page(self, url: str) -> str:
        """Fetch an HTML page (index or denomination page) and return its text."""
        response = self._request("GET", url)
        if response.status_code != 200:
            raise FetchFailed(f"{url}: HTTP {response.status_code}")
        self._check_content_type(response, "html")
        return response.text

    def get_file(self, url: str, ext: str, etag: str = "", last_modified: str = "") -> Fetched | NotModified:
        """Download a result file; returns :class:`NotModified` when the validators say it is unchanged."""
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = self._request("GET", url, headers)
        if response.status_code == 304:
            return NotModified(url=url)
        if response.status_code != 200:
            raise FetchFailed(f"{url}: HTTP {response.status_code}")
        content_type = self._check_content_type(response, ext.lower())
        return Fetched(
            url=str(response.request.url),
            content=response.content,
            sha256=hashlib.sha256(response.content).hexdigest(),
            content_type=content_type,
            etag=response.headers.get("etag", ""),
            last_modified=response.headers.get("last-modified", ""),
        )

    @staticmethod
    def _check_content_type(response: httpx.Response, ext: str) -> str:
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        allowed = EXPECTED_CONTENT_TYPES.get(ext)
        if allowed is None:
            raise UnexpectedContentType(f"Unsupported file type .{ext}")
        if content_type not in allowed:
            raise UnexpectedContentType(f"Content-Type {content_type!r} does not match .{ext}")
        return str(content_type)
