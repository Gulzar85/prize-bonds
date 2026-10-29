"""Compare two revisions of a draw. Pure functions; Django-free so they are trivial to test."""

from collections.abc import Mapping
from typing import Any

HEADER_FIELDS = ("draw_number", "draw_date", "city", "denomination_value")
#: Lists in the stored diff are cut at this length; the counts stay exact.
MAX_LISTED = 200


def compute_diff(
    old_numbers: Mapping[int, set[str]],
    new_numbers: Mapping[int, set[str]],
    old_header: Mapping[str, Any],
    new_header: Mapping[str, Any],
    old_amounts: Mapping[int, int] | None = None,
    new_amounts: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    """Numbers added and removed per tier, header and amount changes, and the share of numbers that changed."""
    tiers: dict[str, Any] = {}
    changed = 0
    total = 0
    for rank in sorted(set(old_numbers) | set(new_numbers)):
        before, after = old_numbers.get(rank, set()), new_numbers.get(rank, set())
        added, removed = sorted(after - before), sorted(before - after)
        changed += len(added) + len(removed)
        total += len(before | after)
        tiers[str(rank)] = {
            "added": added[:MAX_LISTED],
            "removed": removed[:MAX_LISTED],
            "added_count": len(added),
            "removed_count": len(removed),
        }
    header = {
        field: [old_header.get(field), new_header.get(field)]
        for field in HEADER_FIELDS
        if old_header.get(field) != new_header.get(field)
    }
    amounts = {
        str(rank): [(old_amounts or {}).get(rank), (new_amounts or {}).get(rank)]
        for rank in sorted(set(old_amounts or {}) | set(new_amounts or {}))
        if (old_amounts or {}).get(rank) != (new_amounts or {}).get(rank)
    }
    return {
        "tiers": tiers,
        "header": header,
        "amounts": amounts,
        "changed_numbers": changed,
        "ratio": (changed / total) if total else 0.0,
        "is_empty": not changed and not header and not amounts,
    }
