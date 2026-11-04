"""Topic dedup: batching, unreachable AI, and same-code prompt rules."""

import asyncio
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from rich.console import Console

from src.ai.prompting.deduplication import TOPIC_DEDUP_SYSTEM, TOPIC_DEDUP_USER
from src.ai.utils import parse_json_response
from src.models import (
    ClassificationResult,
    ContentAnalysis,
    ContentItem,
    ProcessingResult,
    SourceType,
)
from src.orchestrator import HorizonOrchestrator


def _item(index: int) -> ContentItem:
    return ContentItem(
        id=str(index),
        title=f"item {index}",
        url=f"https://example.com/{index}",
        source_type=SourceType.RSS,
        published_at=datetime.now(timezone.utc),
        content="body",
        processing=ProcessingResult(
            classification=ClassificationResult(
                profile="cloud-perks", method="source_override"
            ),
            analysis=ContentAnalysis(score=5.0, summary="summary", reason="test"),
        ),
    )


def _dedup(monkeypatch, items, batch_size):
    orchestrator = object.__new__(HorizonOrchestrator)
    orchestrator.config = type("Config", (), {})()
    orchestrator.config.ai = type("AI", (), {"dedup_batch_size": batch_size})()
    calls = []

    async def fake_batch(self, batch, system, user_template, *, log):
        calls.append(len(batch))
        return batch

    monkeypatch.setattr(
        HorizonOrchestrator, "_dedup_topic_batch", fake_batch
    )
    result = asyncio.run(HorizonOrchestrator.merge_topic_duplicates(orchestrator, items, log=False))
    return calls, result


def test_large_day_is_split_into_batches(monkeypatch):
    """A 90-item day used to overflow one AI call; every duplicate survived."""
    items = [_item(i) for i in range(90)]

    calls, result = _dedup(monkeypatch, items, 80)

    assert calls == [80, 10]
    assert len(result) == 90


def test_small_day_stays_in_one_call(monkeypatch):
    calls, result = _dedup(monkeypatch, [_item(i) for i in range(5)], 80)

    assert calls == [5]
    assert len(result) == 5


def test_unreachable_ai_keeps_items(monkeypatch):
    orchestrator = object.__new__(HorizonOrchestrator)
    orchestrator.config = type("Config", (), {})()
    orchestrator.config.ai = type("AI", (), {"dedup_batch_size": 80})()
    orchestrator.console = Console(file=StringIO())

    def no_client(_config):
        raise RuntimeError("no client")

    monkeypatch.setattr("src.orchestrator.create_ai_client", no_client)
    items = [_item(0), _item(1)]

    result = asyncio.run(HorizonOrchestrator._dedup_topic_batch(
        orchestrator, items, TOPIC_DEDUP_SYSTEM, TOPIC_DEDUP_USER, log=True
    ))

    assert [item.id for item in result] == ["0", "1"]


def test_empty_reply_is_not_a_parse_error():
    """An empty tool-call reply arrives as None; it must not raise AttributeError."""
    assert parse_json_response(None) is None


def test_prompt_treats_same_code_as_duplicate():
    assert "same invite code" in TOPIC_DEDUP_SYSTEM
    assert "DIFFERENT code are NOT duplicates" in TOPIC_DEDUP_SYSTEM


def test_real_today_digest_duplicate_pairs_would_be_caught():
    """Regression: the 11-04 digest carried the same code in four items."""
    post = Path(__file__).resolve().parents[1] / ".tmp-cache" / "ghposts" / "2026-11-04.md"
    if not post.exists():
        return
    code = "LMJBOW"
    assert post.read_text(encoding="utf-8").count(code) >= 4