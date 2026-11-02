"""Hosted page extractors (Firecrawl / Crawl4AI)."""

import asyncio

import httpx

from src.extractors.crawl4ai import Crawl4AIExtractor
from src.extractors.firecrawl import FirecrawlExtractor
from src.extractors.registry import ExtractorRegistry
from src.models import Crawl4AIExtractorConfig, FirecrawlExtractorConfig


def test_crawl4ai_returns_markdown(monkeypatch) -> None:
    monkeypatch.setenv("CRAWL4AI_API_KEY", "key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = request.url
        return httpx.Response(200, json={"ok": True, "markdown": "# Title\n\nbody"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            extractor = Crawl4AIExtractor(Crawl4AIExtractorConfig())
            return await extractor.extract("https://example.com/a", client)

    text = asyncio.run(run())

    assert text == "# Title\n\nbody"
    assert seen["auth"] == "Bearer key"
    assert str(seen["url"]) == "https://api.crawl4ai.com/scrape"


def test_firecrawl_returns_markdown(monkeypatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": True, "data": {"markdown": "# Hello"}}
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            extractor = FirecrawlExtractor(FirecrawlExtractorConfig())
            return await extractor.extract("https://example.com/a", client)

    assert asyncio.run(run()) == "# Hello"


def test_missing_key_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("CRAWL4AI_API_KEY", raising=False)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
        ) as client:
            extractor = Crawl4AIExtractor(Crawl4AIExtractorConfig())
            return await extractor.extract("https://example.com", client)

    assert asyncio.run(run()) is None


def test_non_200_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "key")

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
        ) as client:
            extractor = FirecrawlExtractor(FirecrawlExtractorConfig())
            return await extractor.extract("https://example.com", client)

    assert asyncio.run(run()) is None


def test_markdown_is_truncated_by_max_chars(monkeypatch) -> None:
    monkeypatch.setenv("CRAWL4AI_API_KEY", "key")

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"markdown": "x" * 500})
            )
        ) as client:
            extractor = Crawl4AIExtractor(Crawl4AIExtractorConfig(max_chars=10))
            return await extractor.extract("https://example.com", client)

    assert asyncio.run(run()) == "x" * 10


def test_registry_builds_both_hosted_extractors(monkeypatch) -> None:
    registry = ExtractorRegistry(
        {
            "firecrawl": FirecrawlExtractorConfig(),
            "crawl4ai": Crawl4AIExtractorConfig(),
        }
    )

    assert isinstance(registry.get("firecrawl"), FirecrawlExtractor)
    assert isinstance(registry.get("crawl4ai"), Crawl4AIExtractor)
    assert registry.get("unknown") is None