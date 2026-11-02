"""Derive candidate search queries from recent digests, validate their yield, and
optionally persist the survivors for the runtime to pick up.

Read-only by default. `--apply` writes data/auto_queries.json (never the main
config), capped per run and expiring after two weeks so a dead term drops out.
"""

import argparse
import calendar
import glob
import json
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
MAX_ADD_PER_RUN = 3
AUTO_TTL_DAYS = 14
TAG_RE = re.compile(r"#\\?#([^`,\s]+)")
ENTITY_RE = re.compile(r"[A-Z][A-Za-z0-9.+-]{2,}")
# A hit only counts when the title also looks like a perk/credit story; without
# this, brand terms match stock prices and product launches.
PERK_RE = re.compile(
    r"免费|额度|赠金|试用|赠送|兑换|领取|白嫖|折扣|优惠|学生|"
    r"credits?|free|trial|giveaway|promo|redeem|coupon|discount|student",
    re.I,
)
# Brands that are too broad to make a useful single-term feed, plus marketing
# words that slip through the capitalised-word heuristic ("ChatGPT Plus").
STOP_ENTITIES = {
    "API", "Cloud", "Pro", "Tokens", "Horizon", "Google", "The", "New",
    "Plus", "Max", "Ultra", "Team", "Business", "Studio", "Beta", "Preview",
    "Starter", "Basic", "Premium", "Agent", "Credit", "Credits", "Trial",
    "Deal", "Deals", "Sale", "Offer", "Free", "Official",
}
CONFIG = Path("data/config.github.json")
AUTO = Path("data/auto_queries.json")
GN = "https://news.google.com/rss/search"


def _allowed(term: str) -> bool:
    """Brand-like token: not a known generic word, long enough to be specific."""
    return term not in STOP_ENTITIES and (
        len(term) >= 5 or any(ch.isdigit() for ch in term)
    )


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
                    if _allowed(word)
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
    hits = [
        entry
        for entry in fresh
        if term.lower() in entry.get("title", "").lower()
        and PERK_RE.search(entry.get("title", ""))
    ]
    return len(hits), [entry.get("title", "")[:70] for entry in hits[:3]]


def report(term: str, count: int, config_text: str, client: httpx.Client) -> str:
    covered = term in config_text
    fresh, samples = validate(term, client)
    verdict = "SKIP covered" if covered else (
        "ADD" if YIELD_MIN <= fresh <= YIELD_MAX else "SKIP yield"
    )
    print(f"\n{count:3d}  {term}  -> {fresh} fresh/72h  [{verdict}]")
    for title in samples:
        print(f"     - {title}")
    return term if verdict == "ADD" else ""


def auto_url(term: str) -> str:
    query = f'"{term}" when:7d'
    return GN + "?" + urllib.parse.urlencode(
        {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    )


def load_auto() -> list[dict]:
    try:
        payload = json.loads(AUTO.read_text(encoding="utf-8"))
        return payload.get("queries") or []
    except (OSError, ValueError, AttributeError):
        return []


def apply(candidates: list[str]) -> None:
    now = datetime.now(timezone.utc)
    live = []
    for entry in load_auto():
        try:
            if _allowed(str(entry.get("term", ""))) and (
                datetime.fromisoformat(entry["expires_at"]) > now
            ):
                live.append(entry)
        except (KeyError, ValueError):
            continue
    known = {entry.get("term") for entry in live}
    added = 0
    for term in candidates:
        if added >= MAX_ADD_PER_RUN or term in known:
            continue
        live.append(
            {
                "term": term,
                "name": f"自动: {term}",
                "url": auto_url(term),
                "added_at": now.isoformat(timespec="seconds"),
                "expires_at": (now + timedelta(days=AUTO_TTL_DAYS)).isoformat(
                    timespec="seconds"
                ),
                "category": "cloud-perks",
                "profile": "cloud-perks",
            }
        )
        known.add(term)
        added += 1
    AUTO.parent.mkdir(parents=True, exist_ok=True)
    AUTO.write_text(
        json.dumps({"queries": live}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\napplied {added} new queries; {len(live)} live entries in {AUTO}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="write ADD terms to data/auto_queries.json"
    )
    args = parser.parse_args()

    os.environ.pop("NO_PROXY", None)
    os.environ.pop("no_proxy", None)
    tags, entities = recent_posts_counts()
    config_text = urllib.parse.unquote(CONFIG.read_text(encoding="utf-8"))
    candidates: list[str] = []
    with httpx.Client(follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        print(f"=== tags in the last {WINDOW_DAYS} days: {len(tags)} distinct ===")
        for term, count in tags.most_common():
            if count >= MIN_TAG_COUNT:
                candidates.append(report(term, count, config_text, c))
        print(f"\n=== entities in selected titles: {len(entities)} distinct ===")
        for term, count in entities.most_common():
            if count >= MIN_ENTITY_COUNT:
                candidates.append(report(term, count, config_text, c))
    if args.apply:
        apply([term for term in candidates if term])


if __name__ == "__main__":
    main()