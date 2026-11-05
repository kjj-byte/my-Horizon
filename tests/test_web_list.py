"""WebListScraper: Crawl4AI /extract rows -> ContentItems."""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from src.models import WebListConfig
from src.scrapers.web_list import WebListScraper


def _config(**kwargs) -> WebListConfig:
    defaults = dict(
        name="测试列表",
        url="https://example.com/list?q=free",
        max_items=5,
        category="cloud-perks",
        profile="cloud-perks",
    )
    defaults.update(kwargs)
    return WebListConfig(**defaults)


def test_extract_rows_become_items(monkeypatch) -> None:
    monkeypatch.setenv("CRAWL4AI_API_KEY", "key")
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [
        {
            "title": "免费领 100 元额度",
            "url": "/deal/1",
            "date": today,
            "summary": "注册即领",
        },
        {"title": "旧活动", "url": "https://example.com/deal/0", "date": "2026-10-01"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/extract"
        assert request.headers.get("authorization") == "Bearer key"
        return httpx.Response(200, json={"ok": True, "data": rows})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scraper = WebListScraper([_config()], client)
            return await scraper.fetch(datetime.now(timezone.utc) - timedelta(days=3))

    items = asyncio.run(run())

    assert len(items) == 1
    assert items[0].title == "免费领 100 元额度"
    assert str(items[0].url) == "https://example.com/deal/1"
    assert items[0].source_type.value == "web_list"
    assert items[0].metadata["source_name"] == "测试列表"


def test_missing_key_returns_empty(monkeypatch) -> None:
    monkeypatch.delenv("CRAWL4AI_API_KEY", raising=False)
    monkeypatch.delenv("CRAWL4AI_API_KEY_2", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected without a key")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scraper = WebListScraper([_config()], client)
            return await scraper.fetch(datetime.now(timezone.utc))

    assert asyncio.run(run()) == []


def test_second_key_used_when_first_has_no_credit(monkeypatch) -> None:
    monkeypatch.setenv("CRAWL4AI_API_KEY", "first")
    monkeypatch.setenv("CRAWL4AI_API_KEY_2", "second")
    today = datetime.now(timezone.utc).date().isoformat()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        if request.headers.get("authorization") == "Bearer first":
            return httpx.Response(402, json={"error": "no_credit"})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "data": [
                    {"title": "item", "url": "https://example.com/1", "date": today}
                ],
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg = _config(api_key_envs=["CRAWL4AI_API_KEY", "CRAWL4AI_API_KEY_2"])
            scraper = WebListScraper([cfg], client)
            return await scraper.fetch(datetime.now(timezone.utc) - timedelta(days=3))

    items = asyncio.run(run())

    assert seen == ["Bearer first", "Bearer second"]
    assert len(items) == 1


def test_rows_without_title_or_url_are_skipped(monkeypatch) -> None:
    monkeypatch.setenv("CRAWL4AI_API_KEY", "key")
    today = datetime.now(timezone.utc).date().isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "data": [
                    {"title": "", "url": "https://example.com/1"},
                    {"title": "no url"},
                    {"title": "ok", "url": "https://example.com/ok", "date": today},
                ],
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scraper = WebListScraper([_config()], client)
            return await scraper.fetch(datetime.now(timezone.utc) - timedelta(days=3))

    assert len(asyncio.run(run())) == 1