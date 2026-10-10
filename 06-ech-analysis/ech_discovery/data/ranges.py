from dataclasses import dataclass
from datetime import date, datetime, timedelta

follow_domain_date = date(2025, 7, 14)


@dataclass(frozen=True)
class TimeRange:
    """Name and start and end-date of observation periods."""

    name: str
    start: date | None = None  # inclusive
    end: date | None = None  # inclusive

    def contains(self, when: datetime | date) -> bool:
        if isinstance(when, datetime):
            when = when.date()
        return (self.start is None or when >= self.start) and (
            self.end is None or when <= self.end
        )

    @property
    def duration(self) -> timedelta | None:
        if self.start is None or self.end is None:
            return None
        # +1 day to consider last day
        return self.end - self.start + timedelta(days=1)

    def expr(self, col: str = "measurement"):
        import polars as pl

        cond = pl.lit(True)
        if self.start is not None:
            cond = cond & (pl.col(col).dt.date() >= self.start)
        if self.end is not None:
            cond = cond & (pl.col(col).dt.date() <= self.end)
        return cond


MAIN = TimeRange("main", start=date(2025, 7, 1), end=date(2025, 11, 6))
FOLLOWUP = TimeRange("followup", start=date(2026, 5, 28), end=date(2026, 8, 15))
ERROR_STATS_MAIN = TimeRange("error-stats", start=follow_domain_date, end=MAIN.end)
ALL = TimeRange("all")

RANGES = {r.name: r for r in (MAIN, FOLLOWUP, ERROR_STATS_MAIN, ALL)}
DEFAULT_RANGES = (MAIN.name, FOLLOWUP.name, ALL.name)
DATED_RANGES = (MAIN.name, FOLLOWUP.name)
