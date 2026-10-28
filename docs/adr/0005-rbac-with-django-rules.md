# ADR-0005: RBAC with django-rules

## Status
Accepted

## Context
We need object-level permissions based on household membership and roles (OWNER, EDITOR, VIEWER).

## Decision
- Use django-rules for predicate-based permissions
- Define predicates: is_member, is_owner, is_editor_or_owner
- Permissions: households.view_household, households.change_household, households.manage_members
- Enforce at service layer and view layer
- Role checks in addition to django-rules where needed

## Consequences
- Flexible, reusable permission logic
- Object-level permissions supported
- Clean separation of concerns
- Easy to test predicates in isolation
- Rules are registered globally
