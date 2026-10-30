"""RSS: if every enabled feed fails, the source must fail loudly, not look empty."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.models import RSSSourceConfig
from src.scrapers.rss import RSSScraper

_SINCE = datetime(2026, 4, 24, 0, 0, tzinfo=timezone.utc)


def test_all_feeds_failing_raises():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    source = RSSSourceConfig(name="x", url="https://example.com/feed.xml", profile="p")
    scraper = RSSScraper([source], client)
    with pytest.raises(RuntimeError, match="RSS feeds failed"):
        asyncio.run(scraper.fetch(_SINCE))


def test_one_feed_working_keeps_result_empty_without_error():
    empty_feed = MagicMock()
    empty_feed.text = "<rss><channel></channel></rss>"
    empty_feed.raise_for_status.return_value = None
    client = AsyncMock()
    client.get = AsyncMock(side_effect=[httpx.ConnectError("boom"), empty_feed])
    sources = [
        RSSSourceConfig(name="a", url="https://a.example/f.xml", profile="p"),
        RSSSourceConfig(name="b", url="https://b.example/f.xml", profile="p"),
    ]
    scraper = RSSScraper(sources, client)
    assert asyncio.run(scraper.fetch(_SINCE)) == []
