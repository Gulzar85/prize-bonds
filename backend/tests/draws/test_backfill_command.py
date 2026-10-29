from io import StringIO

import pytest
import respx
from django.core.management import CommandError, call_command

from apps.draws.models import Draw, DrawRevision, IngestionRun, OutboxEvent
from apps.draws.services import crawl
from tests.draws.conftest import make_operator
from tests.draws.site import Clock, FakeSite, make_fetcher

pytestmark = pytest.mark.django_db


@pytest.fixture
def site(monkeypatch):
    with respx.mock(assert_all_called=False) as router:
        fake = FakeSite(router)
        monkeypatch.setattr(crawl, "make_fetcher", lambda: make_fetcher(Clock()))
        yield fake


def run(*args):
    out, err = StringIO(), StringIO()
    call_command("backfill_draws", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_dry_run_writes_nothing_and_prints_a_findings_summary(site, sent_alerts):
    out, _ = run("--denomination", "rs-200", "--since", "2026", "--dry-run")
    assert "Dry run: 3 files checked, nothing written." in out
    assert "announced_count_is_total" in out
    assert not Draw.objects.exists() and not DrawRevision.objects.exists() and not IngestionRun.objects.exists()


def test_backfill_imports_and_a_rerun_changes_nothing(site, sent_alerts):
    out, _ = run("--denomination", "rs-200", "--since", "2026")
    assert "new files: 3" in out and "NEEDS_REVIEW=3" in out
    assert IngestionRun.objects.get().trigger == "BACKFILL"
    before = list(DrawRevision.objects.order_by("pk").values_list("pk", "sha256"))

    out, _ = run("--denomination", "rs-200", "--since", "2026")
    assert "new files: 0" in out and "unchanged: 3" in out
    assert list(DrawRevision.objects.order_by("pk").values_list("pk", "sha256")) == before
    assert IngestionRun.objects.count() == 2


def test_progress_is_logged_per_draw(site, sent_alerts):
    out, _ = run("--denomination", "rs-200", "--since", "2026")
    assert "rs-200 2026-09-15: new_revision" in out


def test_files_that_cannot_be_fetched_are_reported_on_stderr(site, sent_alerts):
    site.unavailable.add("https://savings.gov.pk/wp-content/uploads/2026/06/Rs-200-15-06-2026-106-draw.txt")
    out, err = run("--denomination", "rs-200", "--since", "2026")
    assert "failed: 1" in out
    assert "2026-06-15" in err


def test_approve_clean_publishes_only_historical_clean_revisions(site, sent_alerts):
    operator = make_operator()
    run("--denomination", "rs-200", "--since", "2026")
    # Real 2026 files all carry warnings (no date/city in the header, total-count wording), so nothing is clean.
    out, _ = run("--denomination", "rs-200", "--since", "2026", "--approve-clean", "--as", operator.email)
    assert "Auto-approved clean historical revisions: 0" in out
    assert not OutboxEvent.objects.exists()


def test_approve_clean_approves_a_genuinely_clean_historical_file(site, sent_alerts):
    operator = make_operator()
    run("--denomination", "rs-200", "--since", "2021")
    clean = [
        r for r in DrawRevision.objects.filter(status="NEEDS_REVIEW") if not r.parse_errors and not r.parse_warnings
    ]
    out, _ = run("--denomination", "rs-200", "--since", "2021", "--approve-clean", "--as", operator.email)
    approved = DrawRevision.objects.filter(status="APPROVED").count()
    assert f"Auto-approved clean historical revisions: {len(clean)}" in out
    assert approved == len(clean)
    assert OutboxEvent.objects.filter(type="draw.published").count() == approved


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--denomination", "rs-5"], "Unknown denomination"),
        (["--approve-clean"], "needs --as"),
        (["--approve-clean", "--as", "nobody@example.com"], "No user"),
        (["--dry-run", "--approve-clean", "--as", "x@example.com"], "cannot be combined"),
    ],
)
def test_bad_arguments_are_refused(site, args, message):
    with pytest.raises(CommandError, match=message):
        run(*args)


def test_approve_clean_requires_a_real_operator(site, sent_alerts):
    from tests.factories import UserFactory

    stranger = UserFactory()
    with pytest.raises(CommandError, match="data operators"):
        run("--denomination", "rs-200", "--since", "2026", "--approve-clean", "--as", stranger.email)
