from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Return the current IST wall-clock time without a timezone suffix for SQLite."""
    return datetime.now(IST).replace(tzinfo=None)


def as_ist_naive(value: datetime) -> datetime:
    """Treat naive values as IST and normalize timezone-aware values to IST."""
    if value.tzinfo is None:
        return value
    return value.astimezone(IST).replace(tzinfo=None)