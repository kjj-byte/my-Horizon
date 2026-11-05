"""Global topic blocks: processing.exclude_* drop items before any AI call."""

import json
from types import SimpleNamespace

from src.orchestrator import HorizonOrchestrator
from src.processing import ProfileRegistry


def _item(title: str, url: str = "https://example.com/a", content: str = "body"):
    return SimpleNamespace(title=title, url=url, content=content)


def _orchestrator(monkeypatch, keywords, url_parts=()):
    orch = object.__new__(HorizonOrchestrator)
    orch.config = SimpleNamespace(
        processing=SimpleNamespace(
            exclude_keywords=list(keywords), exclude_url_substrings=list(url_parts)
        )
    )
    printed = []
    orch.console = SimpleNamespace(print=lambda *a, **k: printed.append(str(a[0]) if a else ""))
    return orch, printed


def test_blocks_a_topic_for_every_profile(monkeypatch):
    """Muse invite-code posts dominated 11-04: no profile may keep them."""
    orch, printed = _orchestrator(monkeypatch, ["Muse"])
    items = [
        _item("Muse 邀请码 LMJBOW：美国用户可领 10 亿 AI Token"),
        _item("Muse AI 智能体邀请奖励：双方各得 10 亿词元", content="MUSE 代币"),
        _item("甲骨文云 2 核 12G 免费 VPS"),
    ]

    kept = orch.drop_excluded_items(items)

    assert [item.title for item in kept] == ["甲骨文云 2 核 12G 免费 VPS"]
    assert any("Dropped 2 excluded items" in line for line in printed)


def test_url_substrings_are_dropped_too():
    orch, _ = _orchestrator(None, [], url_parts=("example.com/spam",))
    items = [_item("ok", url="https://example.com/keep"), _item("spam", url="https://example.com/spam/1")]

    assert [item.title for item in orch.drop_excluded_items(items)] == ["ok"]


def test_nothing_configured_keeps_everything():
    orch, printed = _orchestrator(None, [])
    items = [_item("a"), _item("b")]

    assert orch.drop_excluded_items(items) == items
    assert printed == []


def test_configured_keyword_blocks_muse_posts():
    """Guard the shipped value: it is a plain substring, so "museum" is dropped too."""
    with open("data/config.github.json", encoding="utf-8") as handle:
        doc = json.load(handle)
    keywords = [k.lower() for k in doc["processing"]["exclude_keywords"]]

    assert "muse" in keywords
    # Plain substring match: a museum story would be dropped as well. Accepted
    # for this perks beat; add a word-boundary filter if art/design news matters.
    assert any(k in "museum of modern art" for k in keywords)