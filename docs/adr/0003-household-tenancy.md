# ADR-0003: Household-Based Multi-Tenancy

## Status
Accepted

## Context
We need strict data isolation between families/households. All bond data must never leak across households.

## Decision
- Tenant = Household
- Every user belongs to households via Membership with roles (OWNER, EDITOR, VIEWER)
- All household-scoped data inherits from HouseholdScopedModel
- HouseholdScopedViewMixin enforces membership and scoping
- On email verification, users get a personal household automatically
- 404 (not 403) for cross-tenant access to prevent information leakage

## Consequences
- Strong tenant isolation by design
- Some queries require joins through memberships
- Need careful enforcement at model, view, and query levels
- Meta-tests enforce mixin usage
- Slightly more complex queries but much more secure

## Addendum: enforcement details
- Non-members (and unknown or soft-deleted households) receive **404**, members lacking a permission receive **403**.
- `HouseholdScopedViewMixin` resolves the household from `/households/{household_id}/...`; a meta-test fails if
  any view under that prefix, or serving a `HouseholdScopedModel`, does not use it.
- Foreign keys into `Household` use Django 6.1 `DB_CASCADE`. Django forbids mixing Python and database `on_delete`
  variants in one reference chain, so `Household.created_by` uses `DO_NOTHING` (the database FK still blocks
  deleting a user who created a household).
- Project-wide default manager sets `FETCH_PEERS` (6.1 fetch modes) so lazy related access never becomes N+1.
- "At least one owner" cannot be a row-level CHECK; it is enforced in `households.services` under a row lock and tested.
