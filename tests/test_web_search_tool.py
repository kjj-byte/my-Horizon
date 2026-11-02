"""web_search: a flaky DuckDuckGo must not silently drop every lookup."""

import asyncio

from src.processing import tools
from src.processing.tools import WebSearchTool


def _fake(monkeypatch, script):
    """script: list of ("raise"|"empty"|"hit", backend-aware) results per call."""
    calls: list[str | None] = []

    class FakeDDGS:
        def text(self, query, **kwargs):
            backend = kwargs.get("backend")
            calls.append(backend)
            action = script[len(calls) - 1]
            if action == "raise":
                raise RuntimeError("rate limited")
            if action == "empty":
                return []
            return [{"title": "Free credits", "href": "https://example.com/x", "body": "b"}]

    monkeypatch.setattr(tools, "DDGS", FakeDDGS)
    monkeypatch.setattr(WebSearchTool, "_RETRY_DELAY", 0)
    return calls


def test_retries_with_another_backend(monkeypatch):
    calls = _fake(monkeypatch, ["raise", "hit"])

    results = asyncio.run(WebSearchTool().execute({"query": "free credits"}))

    assert [r["url"] for r in results] == ["https://example.com/x"]
    assert calls == [None, "brave"]


def test_empty_result_is_not_reported_as_failure(monkeypatch):
    calls = _fake(monkeypatch, ["empty", "hit"])

    results = asyncio.run(WebSearchTool().execute({"query": "free credits"}))

    assert len(results) == 1
    assert len(calls) == 2


def test_all_backends_failing_returns_empty(monkeypatch, caplog):
    calls = _fake(monkeypatch, ["raise", "raise", "raise"])

    results = asyncio.run(WebSearchTool().execute({"query": "free credits"}))

    assert results == []
    assert len(calls) == len(WebSearchTool._BACKENDS)
    assert "web_search failed" in caplog.text


def test_empty_query_is_rejected():
    try:
        asyncio.run(WebSearchTool().execute({"query": "  "}))
    except ValueError as exc:
        assert "non-empty" in str(exc)
    else:  # pragma: no cover - the assertion above is the real check
        raise AssertionError("expected ValueError")