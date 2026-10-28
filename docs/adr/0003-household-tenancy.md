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
