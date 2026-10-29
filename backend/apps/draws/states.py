"""Allowed state transitions for draws and revisions.

All status changes go through :func:`transition`; anything not listed here is illegal and raises.
"""

from apps.draws.models import Draw, DrawRevision

R = DrawRevision.Status
D = Draw.Status

REVISION_TRANSITIONS: dict[str, frozenset[str]] = {
    R.PENDING: frozenset({R.NEEDS_REVIEW, R.PARSE_FAILED}),
    R.PARSE_FAILED: frozenset({R.REJECTED}),
    R.NEEDS_REVIEW: frozenset({R.APPROVED, R.REJECTED}),
    R.APPROVED: frozenset({R.SUPERSEDED}),
    R.REJECTED: frozenset(),
    R.SUPERSEDED: frozenset(),
}

DRAW_TRANSITIONS: dict[str, frozenset[str]] = {
    D.DISCOVERED: frozenset({D.IN_REVIEW, D.FAILED}),
    D.IN_REVIEW: frozenset({D.PUBLISHED, D.FAILED}),
    D.FAILED: frozenset({D.IN_REVIEW}),
    D.PUBLISHED: frozenset(),
}


class IllegalTransition(Exception):
    def __init__(self, kind: str, current: str, target: str) -> None:
        super().__init__(f"Illegal {kind} transition {current} -> {target}")
        self.kind, self.current, self.target = kind, current, target


def check_transition(table: dict[str, frozenset[str]], kind: str, current: str, target: str) -> None:
    if target not in table.get(current, frozenset()):
        raise IllegalTransition(kind, current, target)


def check_revision_transition(current: str, target: str) -> None:
    check_transition(REVISION_TRANSITIONS, "revision", current, target)


def check_draw_transition(current: str, target: str) -> None:
    check_transition(DRAW_TRANSITIONS, "draw", current, target)
