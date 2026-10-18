"""Sync and auto-merge latest community preset sources into Horizon config."""

import argparse
import sys
from pathlib import Path
from typing import Dict, List

from src.models import (
    Config,
    GitHubSourceConfig,
    RSSSourceConfig,
    RedditSubredditConfig,
    RedditUserConfig,
    TelegramChannelConfig,
)
from src.setup.presets import fetch_presets
from src.storage.manager import StorageManager


def _gh_key(src: GitHubSourceConfig) -> str:
    if src.type == "user_events":
        return f"user:{src.username}"
    return f"repo:{src.owner}/{src.repo}"


def _merge_source_list(new_sources, existing_sources, key):
    merged_by_key = {}
    for source in existing_sources or []:
        source_key = key(source)
        merged_by_key.setdefault(source_key, source.model_copy(deep=True))
    added = 0
    for source in new_sources or []:
        source_key = key(source)
        if source_key not in merged_by_key:
            merged_by_key[source_key] = source.model_copy(deep=True)
            added += 1
    return list(merged_by_key.values()), added


def sync_config(config_path: Path) -> int:
    if not config_path.exists():
        print(f"[Skip] Config file does not exist: {config_path}")
        return 0

    storage = StorageManager(config_path=str(config_path))
    try:
        config = storage.load_config()
    except Exception as e:
        print(f"[Error] Failed to load config {config_path}: {e}")
        return 0

    print(f"Fetching community presets from horizon-site...")
    presets = fetch_presets()
    if not presets or "domains" not in presets:
        print("[Warning] Failed to fetch presets from community API, keeping existing config.")
        return 0

    # Build new source models from presets
    new_github: List[GitHubSourceConfig] = []
    new_rss: List[RSSSourceConfig] = []
    new_subreddits: List[RedditSubredditConfig] = []
    new_reddit_users: List[RedditUserConfig] = []
    new_telegrams: List[TelegramChannelConfig] = []

    for domain in presets.get("domains", []):
        for src in domain.get("sources", []):
            src_type = src.get("type", "")
            cfg = src.get("config", {})

            if src_type == "github_user":
                new_github.append(GitHubSourceConfig(
                    type="user_events",
                    username=cfg.get("username", ""),
                    enabled=True,
                ))
            elif src_type == "github_repo":
                new_github.append(GitHubSourceConfig(
                    type="repo_releases",
                    owner=cfg.get("owner", ""),
                    repo=cfg.get("repo", ""),
                    enabled=True,
                ))
            elif src_type == "rss":
                new_rss.append(RSSSourceConfig(
                    name=cfg.get("name", ""),
                    url=cfg.get("url", ""),
                    enabled=True,
                    category=cfg.get("category", ""),
                ))
            elif src_type == "reddit_subreddit":
                new_subreddits.append(RedditSubredditConfig(
                    subreddit=cfg.get("subreddit", ""),
                    sort=cfg.get("sort", "hot"),
                    fetch_limit=cfg.get("fetch_limit", 15),
                    min_score=cfg.get("min_score", 50),
                ))
            elif src_type == "reddit_user":
                new_reddit_users.append(RedditUserConfig(
                    username=cfg.get("username", ""),
                ))
            elif src_type == "telegram":
                new_telegrams.append(TelegramChannelConfig(
                    channel=cfg.get("channel", ""),
                    fetch_limit=cfg.get("fetch_limit", 20),
                ))

    # Merge sources into existing config
    merged = config.model_copy(deep=True)

    merged.sources.github, added_gh = _merge_source_list(
        new_github, config.sources.github, _gh_key
    )
    merged.sources.rss, added_rss = _merge_source_list(
        new_rss, config.sources.rss, lambda s: str(s.url)
    )
    merged.sources.reddit.subreddits, added_subs = _merge_source_list(
        new_subreddits, config.sources.reddit.subreddits, lambda s: s.subreddit
    )
    merged.sources.reddit.users, added_rusers = _merge_source_list(
        new_reddit_users, config.sources.reddit.users, lambda s: s.username
    )
    merged.sources.telegram.channels, added_tg = _merge_source_list(
        new_telegrams, config.sources.telegram.channels, lambda s: s.channel
    )

    total_added = added_gh + added_rss + added_subs + added_rusers + added_tg

    if total_added > 0:
        storage.save_config(merged, backup=False)
        print(
            f"[Success] {config_path.name}: Merged {total_added} new sources from community "
            f"(RSS: +{added_rss}, GitHub: +{added_gh}, Reddit: +{added_subs}, Telegram: +{added_tg})."
        )
    else:
        print(f"[Up-to-date] {config_path.name}: All community sources already present.")

    return total_added


def main():
    parser = argparse.ArgumentParser(description="Sync and auto-merge latest community preset sources")
    parser.add_argument("--config", type=str, default=None, help="Path to specific config file")
    args = parser.parse_args()

    if args.config:
        sync_config(Path(args.config))
    else:
        # Default sync both local and github configs
        sync_config(Path("data/config.json"))
        sync_config(Path("data/config.github.json"))


if __name__ == "__main__":
    main()
