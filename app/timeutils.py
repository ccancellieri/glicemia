"""Time helpers — the DB stores naive UTC datetimes."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC now (datetime.utcnow is deprecated since Python 3.12).

    Keeps naive-UTC semantics so comparisons against stored naive
    datetimes stay valid; switching to aware datetimes is a separate,
    schema-aware migration.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
