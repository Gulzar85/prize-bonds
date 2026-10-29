"""Plain data types shared by the parser and validators. No Django imports."""

import datetime
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    context: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity.value, "message": self.message, "context": self.context}


@dataclass(frozen=True)
class ParsedTier:
    rank: int
    amount_pkr: int | None
    announced_count: int | None
    numbers: tuple[str, ...]
    filler_count: int = 0


@dataclass(frozen=True)
class ParseResult:
    header_text: str
    draw_number: int | None
    draw_date: datetime.date | None
    city: str | None
    denomination_value: int | None
    tiers: tuple[ParsedTier, ...]
    #: How many cells the third-prize grid had in total (numbers plus filler), when a grid was found.
    grid_cells: int
    #: "N Prizes in each series" total from an official Part-I summary, when present (all tiers).
    announced_total: int | None = None
    warnings: tuple[Finding, ...] = ()

    def tier(self, rank: int) -> ParsedTier | None:
        return next((t for t in self.tiers if t.rank == rank), None)

    def header_dict(self) -> dict[str, Any]:
        return {
            "header_text": self.header_text,
            "draw_number": self.draw_number,
            "draw_date": self.draw_date.isoformat() if self.draw_date else None,
            "city": self.city,
            "denomination_value": self.denomination_value,
        }
