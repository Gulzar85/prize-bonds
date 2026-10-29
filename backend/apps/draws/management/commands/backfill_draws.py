"""Import every historical draw from savings.gov.pk.

    python manage.py backfill_draws [--denomination SLUG] [--since YEAR] [--dry-run] [--approve-clean --as EMAIL]

Idempotent and resumable: each draw is committed on its own, files already stored are skipped (conditional GET and
checksum), so an interrupted run can simply be started again. ``--dry-run`` downloads, parses and validates but writes
nothing, then prints a findings summary.
"""

import collections
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.draws.models import Denomination, DrawRevision, IngestionRun
from apps.draws.services import crawl, review


class Command(BaseCommand):
    help = "Backfill historical draws (idempotent; --dry-run writes nothing)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--denomination", action="append", metavar="SLUG", help="Only this denomination (repeatable)"
        )
        parser.add_argument("--since", type=int, metavar="YEAR", help="Only draws from this year onwards")
        parser.add_argument("--dry-run", action="store_true", help="Parse and validate without writing anything")
        parser.add_argument("--approve-clean", action="store_true", help="Bulk-approve clean historical revisions")
        parser.add_argument("--as", dest="operator", metavar="EMAIL", help="Data operator performing --approve-clean")

    def handle(self, *args: Any, **options: Any) -> None:
        slugs = options["denomination"] or None
        if slugs:
            known = set(Denomination.objects.values_list("slug", flat=True))
            unknown = sorted(set(slugs) - known)
            if unknown:
                raise CommandError(f"Unknown denomination(s): {', '.join(unknown)}. Known: {', '.join(sorted(known))}")
        operator = None
        if options["approve_clean"]:
            if options["dry_run"]:
                raise CommandError("--approve-clean cannot be combined with --dry-run")
            if not options["operator"]:
                raise CommandError("--approve-clean needs --as EMAIL (a data operator with MFA)")
            try:
                operator = get_user_model().objects.get(email__iexact=options["operator"])
            except get_user_model().DoesNotExist as exc:
                raise CommandError(f"No user {options['operator']}") from exc

        fetcher = crawl.make_fetcher()
        try:
            result = crawl.run_crawl(
                fetcher,
                IngestionRun.Trigger.BACKFILL,
                slugs=slugs,
                since_year=options["since"],
                dry_run=options["dry_run"],
                progress=lambda line: self.stdout.write(line),
            )
        finally:
            fetcher.close()

        stats = result.stats
        if options["dry_run"]:
            self._print_dry_run(stats)
            return

        self.stdout.write(
            f"\nPages fetched: {stats.pages_fetched}  new files: {stats.files_new}  unchanged: {stats.files_unchanged}  "
            f"failed: {stats.files_failed}  undated links: {stats.undated_links}"
        )
        for error in stats.errors:
            self.stderr.write(f"  ! {error}")

        if operator is not None:
            try:
                bulk = review.bulk_approve_clean_backfill(operator)
            except review.ReviewError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"Auto-approved clean historical revisions: {bulk.approved}")
        self._print_status_summary()

    def _print_dry_run(self, stats: crawl.CrawlStats) -> None:
        statuses = collections.Counter(str(row["status"]) for row in stats.dry_rows)
        codes: collections.Counter[str] = collections.Counter()
        for row in stats.dry_rows:
            codes.update(row.get("errors", []))  # type: ignore[arg-type]
            codes.update(row.get("warnings", []))  # type: ignore[arg-type]
        self.stdout.write(f"\nDry run: {len(stats.dry_rows)} files checked, nothing written.")
        for status, count in sorted(statuses.items()):
            self.stdout.write(f"  {status:<12}{count}")
        if codes:
            self.stdout.write("Findings:")
            for code, count in codes.most_common():
                self.stdout.write(f"  {code:<36}{count}")
        for error in stats.errors:
            self.stderr.write(f"  ! {error}")

    def _print_status_summary(self) -> None:
        by_status = collections.Counter(DrawRevision.objects.values_list("status", flat=True))
        self.stdout.write("Revisions by status: " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
