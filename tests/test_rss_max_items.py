"""RSS feeds: a noisy feed must be capped per feed without hinting at the global count."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.models import RSSSourceConfig
from src.scrapers.rss import RSSScraper

_SINCE = datetime(2026, 4, 24, 0, 0, tzinfo=timezone.utc)


def _feed(count: int) -> str:
    items = "".join(
        f"<item><guid>g{i}</guid><title>Item {i}</title>"
        f"<link>https://example.com/{i}</link>"
        "<pubDate>Fri, 24 Apr 2026 12:00:00 GMT</pubDate></item>"
        for i in range(count)
    )
    return f'<?xml version="1.0" ?><rss version="2.0"><channel>{items}</channel></rss>'


def _client(feed_text: str) -> AsyncMock:
    response = MagicMock()
    response.content = feed_text.encode()
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.get.return_value = response
    return client


def test_max_items_caps_a_noisy_feed() -> None:
    scraper = RSSScraper(
        [RSSSourceConfig(name="noisy", url="https://example.com/f.xml", max_items=2)],
        _client(_feed(5)),
    )

    items = asyncio.run(scraper.fetch(_SINCE))

    assert len(items) == 2


def test_max_items_none_keeps_everything() -> None:
    scraper = RSSScraper(
        [RSSSourceConfig(name="all", url="https://example.com/f.xml")],
        _client(_feed(3)),
    )

    assert len(asyncio.run(scraper.fetch(_SINCE))) == 3