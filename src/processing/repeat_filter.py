"""Drop content that already appeared in the previous daily digests.

The fetch window is 72h, so without this every story from yesterday's digest is
fetched and re-selected again today.
"""

import logging
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urldefrag

logger = logging.getLogger(__name__)

REPEAT_DIGEST_DAYS = 3

_POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-summary-\w+\.md$")
# Digest items are written as "## [title](url)" or "### [title](url)".
_ITEM_URL = re.compile(r"^#{2,3} \[.+?\]\((https?://[^)\s]+)\)", re.MULTILINE)


def digest_url_key(url: str) -> str:
    """Identity of a link across digests: ignore fragment, trailing slash, case."""
    return urldefrag(url)[0].rstrip("/").lower()


def recent_digest_urls(
    posts_dir: Path, today: date, days: int = REPEAT_DIGEST_DAYS
) -> set[str]:
    """URLs published in the `days` digests before `today`.

    Today's own digest is excluded so a re-run of the same day does not filter
    out everything it just published.
    """
    urls: set[str] = set()
    start = today - timedelta(days=days)
    if not posts_dir.is_dir():
        logger.warning(
            "Repeat filter has no digest directory at %s; repeats are not filtered.",
            posts_dir,
        )
        return urls
    for path in posts_dir.glob("*-summary-*.md"):
        match = _POST_NAME.match(path.name)
        if not match:
            continue
        try:
            digest_date = date.fromisoformat(match[1])
        except ValueError:
            continue
        if not start <= digest_date < today:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            logger.warning("Could not read digest %s: %s", path.name, exc)
            continue
        urls.update(digest_url_key(url) for url in _ITEM_URL.findall(text))
    return urls