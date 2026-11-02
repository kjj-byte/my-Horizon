"""Calendar dates for dated output, in the configured display time zone."""

from datetime import datetime
from zoneinfo import ZoneInfo


def calendar_date(timezone_name: str) -> str:
    """Today's date in the configured zone, not UTC.

    A 07:00 Beijing run happens at 23:00 UTC the day before; naming the summary
    after the UTC day would label it with yesterday's date.
    """
    return datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")