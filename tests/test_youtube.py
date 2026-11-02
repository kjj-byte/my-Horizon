import asyncio
from datetime import datetime, timezone

import httpx

from src.models import YouTubeConfig, YouTubeQueryConfig
from src.scrapers.youtube import YouTubeScraper

SINCE = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)


def _payload(video_id: str, published: str, title: str = "Free credits") -> dict:
    return {
        "items": [
            {
                "id": {"videoId": video_id},
                "snippet": {
                    "publishedAt": published,
                    "title": title,
                    "description": "free stuff",
                    "channelId": "UC-1",
                    "channelTitle": "Deals channel",
                },
            }
        ]
    }


def test_fetch_returns_items_and_filters_old_videos(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(
            200,
            json={
                "items": [
                    _payload("new", "2026-11-01T10:00:00Z")["items"][0],
                    _payload("old", "2026-10-01T10:00:00Z")["items"][0],
                ]
            },
            request=request,
        )

    async def fetch_items():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scraper = YouTubeScraper(
                YouTubeConfig(
                    enabled=True,
                    max_results=5,
                    queries=[YouTubeQueryConfig(query="free credits", language="en")],
                ),
                client,
            )
            return await scraper.fetch(SINCE)

    items = asyncio.run(fetch_items())

    assert [item.id for item in items] == ["youtube:search:new"]
    assert str(items[0].url) == "https://www.youtube.com/watch?v=new"
    assert items[0].author == "Deals channel"
    assert items[0].published_at > SINCE
    assert "publishedAfter=2026-10-30T00%3A00%3A00Z" in str(calls[0])


def test_fetch_enriches_with_videos_list_details(monkeypatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/videos"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "vid1",
                            "snippet": {"description": "Intro\n00:00 开始\n01:00 演示"},
                            "contentDetails": {"duration": "PT1H2M3S"},
                            "statistics": {"viewCount": "123456", "likeCount": "99"},
                        }
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200, json=_payload("vid1", "2026-11-01T10:00:00Z"), request=request
        )

    async def fetch_items():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False
        ) as client:
            scraper = YouTubeScraper(
                YouTubeConfig(
                    enabled=True,
                    max_results=5,
                    queries=[YouTubeQueryConfig(query="free credits")],
                ),
                client,
            )
            return await scraper.fetch(SINCE)

    items = asyncio.run(fetch_items())

    assert len(items) == 1
    assert "00:00 开始" in items[0].content
    assert "时长 1:02:03" in items[0].content
    assert "播放 123,456" in items[0].content
    assert items[0].metadata["duration"] == "PT1H2M3S"


def test_fetch_raises_when_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    async def fetch_items():
        async with httpx.AsyncClient(trust_env=False) as client:
            scraper = YouTubeScraper(
                YouTubeConfig(
                    enabled=True,
                    queries=[YouTubeQueryConfig(query="free credits")],
                ),
                client,
            )
            return await scraper.fetch(SINCE)

    try:
        asyncio.run(fetch_items())
    except RuntimeError as exc:
        assert "YOUTUBE_API_KEY is not set" in str(exc)
    else:
        raise AssertionError("Expected a missing-key error")