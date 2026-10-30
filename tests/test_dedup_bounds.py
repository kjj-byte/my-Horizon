"""AI topic-dedup must not crash when the model returns bad indices."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.orchestrator import HorizonOrchestrator


class _Analysis:
    tags: list = []
    summary = "s"


def _item(title: str) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        processing=SimpleNamespace(analysis=_Analysis()),
        content="c",
        source_type=SimpleNamespace(value="rss"),
    )


def _orchestrator() -> HorizonOrchestrator:
    orch = object.__new__(HorizonOrchestrator)
    orch.config = SimpleNamespace(ai=SimpleNamespace())
    orch.console = SimpleNamespace(print=lambda *a, **k: None)
    return orch


def _patch_ai(monkeypatch, payload: str) -> None:
    class _Stub:
        async def complete(self, **kwargs):
            return payload

    monkeypatch.setattr("src.orchestrator.create_ai_client", lambda cfg: _Stub())


def test_non_integer_primary_index_is_ignored(monkeypatch):
    _patch_ai(monkeypatch, '{"duplicates": [["0", 1]]}')
    items = [_item("a"), _item("b")]
    out = asyncio.run(_orchestrator().merge_topic_duplicates(items, log=False))
    assert len(out) == 2


def test_valid_group_still_drops_duplicate(monkeypatch):
    _patch_ai(monkeypatch, '{"duplicates": [[0, 1]]}')
    items = [_item("a"), _item("b")]
    out = asyncio.run(_orchestrator().merge_topic_duplicates(items, log=False))
    assert len(out) == 1
    assert out[0].title == "a"
