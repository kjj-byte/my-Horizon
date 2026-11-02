"""Merge auto-derived feed queries into the loaded config.

Auto queries live in their own file (data/auto_queries.json) so the hand-written
config stays untouched. Expired entries are ignored, a broken file never blocks
the run, and duplicates are skipped by URL.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from ..models import Config, RSSSourceConfig


def merge_auto_queries(config: Config, path: Path) -> int:
    """Append non-expired auto feeds to ``config.sources.rss``.

    Returns:
        Number of feeds added.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    now = datetime.now(timezone.utc)
    existing = {str(feed.url) for feed in config.sources.rss}
    added = 0
    for entry in payload.get("queries") or []:
        try:
            expires = datetime.fromisoformat(entry["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now or entry["url"] in existing:
                continue
            config.sources.rss.append(
                RSSSourceConfig(
                    name=entry["name"],
                    url=entry["url"],
                    profile=entry.get("profile", "cloud-perks"),
                    category=entry.get("category", "cloud-perks"),
                )
            )
            existing.add(entry["url"])
            added += 1
        except (KeyError, ValueError, TypeError):
            continue
    return added