# ADR-0008: Review, publication and the outbox

## Status
Accepted (Phase 1)

## Decision
- **Nothing is published without a human.** Parsed revisions land in `NEEDS_REVIEW`. Transitions live in
  `apps/draws/states.py` as explicit tables (revision: PENDING to NEEDS_REVIEW or PARSE_FAILED, NEEDS_REVIEW to
  APPROVED or REJECTED, APPROVED to SUPERSEDED; draw: DISCOVERED to IN_REVIEW or FAILED, IN_REVIEW to PUBLISHED or FAILED,
  FAILED to IN_REVIEW); anything else raises `IllegalTransition`.
- **Who may review**: the global `data_operator` group *and* MFA enabled, enforced in the django-rules predicate
  (`is_data_operator & has_mfa`) and checked through the rules registry directly so superusers do not bypass it.
- **Approving** (one transaction, rows locked): the previously published revision becomes SUPERSEDED, the revision becomes
  APPROVED with reviewer, time and mandatory note, the draw's `published_revision` moves, and an `OutboxEvent`
  (`draw.published` for the first publication, `draw.revised` with the diff afterwards) is written. If any step fails nothing
  changes.
- **ERROR findings** block approval unless the reviewer ticks "override" and writes a note (prefixed `[override]` in the record).
- **Four-eyes** (`DRAWS_FOUR_EYES`, on in production): for a manual upload the approver must differ from the uploader.
- **Clean-backfill auto-approval** (`DRAWS_AUTO_APPROVE_CLEAN_BACKFILL`): a data operator may bulk-approve historical,
  first-publication revisions with zero findings, not OCR, not manual uploads. Live draws (newer than
  `DRAWS_HISTORICAL_AFTER_DAYS`) and revisions of published draws are never eligible.
- **Rollback means approving a corrected revision**, never deleting. Foreign keys into the revision chain are `DO_NOTHING`
  (the database still refuses deletes) except tier and number to revision, which use Django 6.1 `DB_CASCADE` as pure data
  integrity. Django forbids mixing database and Python `on_delete` variants in one reference chain, which is why the other
  references use `DO_NOTHING`.
- **Audit**: `Draw` and `DrawRevision` are registered with django-auditlog; every status change and approval is logged.
- **Outbox**: events are written in the publishing transaction; a Celery task (every minute) logs and marks them processed in
  Phase 1. Phase 2's matcher replaces the consumer and decides how `draw.revised` un-notifies or re-notifies users.
- **`GeneratedField`** was evaluated and not used: no query became simpler with it, so it is not justified.
- **Alerts** (Sentry plus email to data operators): draw not found 3 days after its scheduled date, parse or extraction
  failure, unknown denomination, unknown layout, a revision on a published draw, a review waiting more than 24 hours, fetch
  failure. Each fires once per condition where repeats would be noise.

## Consequences
- The review screen is the control point: it shows announced vs parsed counts, findings, source excerpts, 20 sampled numbers
  beside their source lines and the diff.
- Reviewers can publish a file with errors only with a recorded override, which keeps an escape hatch for source typos
  (for example the 4-digit number in Rs 750 draw 108) without losing the paper trail.
