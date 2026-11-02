"""Derive candidate search queries from recent digests, then validate their yield.

Read-only: prints proposals, never edits config. Run weekly and copy the terms
worth keeping into data/config.github.json.
"""

import calendar
import glob
import os
import re
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx

WINDOW_DAYS = 14
FRESH_HOURS = 72
MIN_TAG_COUNT = 2
MIN_ENTITY_COUNT = 3
# A term is worth a feed only when it returns a few fresh items, not zero and
# not a flood that would swamp the digest.
YIELD_MIN, YIELD_MAX = 3, 40
TAG_RE = re.compile(r"#\\?#([^`,\s]+)")
ENTITY_RE = re.compile(r"[A-Z][A-Za-z0-9.+-]{2,}")
# Brands that are too broad to make a useful single-term feed.
STOP_ENTITIES = {"API", "Cloud", "Pro", "Tokens", "Horizon", "Google", "The", "New"}
CONFIG = Path("data/config.github.json")
GN = "https://news.google.com/rss/search"


def recent_posts() -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    posts = []
    for path in glob.glob("docs/_posts/*-summary-*.md"):
        stamp = re.search(r"(\d{4}-\d{2}-\d{2})", path)
        if not stamp:
            continue
        if datetime.fromisoformat(stamp.group(1)).replace(tzinfo=timezone.utc) < cutoff:
            continue
        posts.append(path)
    return posts


def recent_posts_counts() -> tuple[Counter, Counter]:
    tags: Counter = Counter()
    entities: Counter = Counter()
    for path in recent_posts():
        for line in open(path, encoding="utf-8"):
            if line.startswith("**标签**") or line.startswith("**Tags**"):
                tags.update(tag.strip() for tag in TAG_RE.findall(line))
                continue
            title = re.match(r"^### \[(.*?)\]", line)
            if title:
                entities.update(
                    word
                    for word in ENTITY_RE.findall(title.group(1))
                    if word not in STOP_ENTITIES
                )
    return tags, entities


def validate(term: str, client: httpx.Client) -> tuple[int, list[str]]:
    resp = client.get(
        GN,
        params={
            "q": f'"{term}" when:7d',
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
        },
        timeout=30,
    )
    resp.raise_for_status()
    since = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    fresh = [
        entry
        for entry in feedparser.parse(resp.text).entries
        if entry.get("published_parsed")
        and datetime.fromtimestamp(
            calendar.timegm(entry.published_parsed), tz=timezone.utc
        )
        >= since
    ]
    # Google News matches fuzzily; only count items whose title actually carries
    # the term, otherwise "开发者大赛" counts unrelated regional news.
    hits = [entry for entry in fresh if term.lower() in entry.get("title", "").lower()]
    return len(hits), [entry.get("title", "")[:70] for entry in hits[:3]]


def report(term: str, count: int, config_text: str, client: httpx.Client) -> None:
    covered = term in config_text
    fresh, samples = validate(term, client)
    verdict = "SKIP covered" if covered else (
        "ADD" if YIELD_MIN <= fresh <= YIELD_MAX else "SKIP yield"
    )
    print(f"\n{count:3d}  {term}  -> {fresh} fresh/72h  [{verdict}]")
    for title in samples:
        print(f"     - {title}")


def main() -> None:
    os.environ.pop("NO_PROXY", None)
    os.environ.pop("no_proxy", None)
    tags, entities = recent_posts_counts()
    config_text = urllib.parse.unquote(CONFIG.read_text(encoding="utf-8"))
    with httpx.Client(follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        print(f"=== tags in the last {WINDOW_DAYS} days: {len(tags)} distinct ===")
        for term, count in tags.most_common():
            if count >= MIN_TAG_COUNT:
                report(term, count, config_text, c)
        print(f"\n=== entities in selected titles: {len(entities)} distinct ===")
        for term, count in entities.most_common():
            if count >= MIN_ENTITY_COUNT:
                report(term, count, config_text, c)


if __name__ == "__main__":
    main()