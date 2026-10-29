"""Permissions for the draw engine. Draw data is global, so these are global (not per-household) rules.

Data operators must have MFA enabled; the rule fails closed without it, so a stolen password alone can never
publish a result.
"""

import rules
from allauth.mfa.utils import is_mfa_enabled
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import User

DATA_OPERATOR_GROUP = "data_operator"


@rules.predicate
def is_data_operator(user: User | AnonymousUser) -> bool:
    return bool(user.is_authenticated and user.is_active and user.groups.filter(name=DATA_OPERATOR_GROUP).exists())


@rules.predicate
def has_mfa(user: User | AnonymousUser) -> bool:
    return bool(user.is_authenticated and is_mfa_enabled(user))


rules.add_perm("draws.review_revision", is_data_operator & has_mfa)
rules.add_perm("draws.upload_revision", is_data_operator & has_mfa)


def can_review(user: User | AnonymousUser) -> bool:
    """Check through the rules registry directly: superusers do not bypass the MFA requirement."""
    return bool(rules.has_perm("draws.review_revision", user))


def can_upload(user: User | AnonymousUser) -> bool:
    return bool(rules.has_perm("draws.upload_revision", user))
