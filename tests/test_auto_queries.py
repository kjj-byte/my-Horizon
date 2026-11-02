"""Auto-derived feed queries merge into the loaded config."""

import json
from datetime import datetime, timedelta, timezone

from src.models import Config
from src.processing.auto_queries import merge_auto_queries


def make_config() -> Config:
    return Config.model_validate(
        {
            "ai": {"provider": "openai", "model": "test", "api_key_env": "KEY"},
            "collection": {},
            "digest": {},
            "sources": {"rss": [{"name": "Feed", "url": "https://example.com/feed"}]},
        }
    )


def test_merge_adds_live_and_skips_expired_and_duplicate(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    auto = tmp_path / "auto_queries.json"
    auto.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "name": "live",
                        "url": "https://example.com/live",
                        "expires_at": (now + timedelta(days=3)).isoformat(),
                    },
                    {
                        "name": "expired",
                        "url": "https://example.com/expired",
                        "expires_at": (now - timedelta(days=1)).isoformat(),
                    },
                    {
                        "name": "dup",
                        "url": "https://example.com/feed",
                        "expires_at": (now + timedelta(days=3)).isoformat(),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    config = make_config()
    assert merge_auto_queries(config, auto) == 1
    assert [str(feed.url) for feed in config.sources.rss] == [
        "https://example.com/feed",
        "https://example.com/live",
    ]


def test_merge_tolerates_missing_and_broken_file(tmp_path) -> None:
    config = make_config()
    assert merge_auto_queries(config, tmp_path / "missing.json") == 0

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert merge_auto_queries(config, broken) == 0
    assert len(config.sources.rss) == 1


def test_merge_skips_entries_without_required_fields(tmp_path) -> None:
    auto = tmp_path / "auto_queries.json"
    auto.write_text(
        json.dumps({"queries": [{"name": "no url"}, {"url": "https://example.com/x"}]}),
        encoding="utf-8",
    )
    config = make_config()
    assert merge_auto_queries(config, auto) == 0