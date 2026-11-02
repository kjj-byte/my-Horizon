"""Discover YouTube channels and keywords for the perks beat.

Searches YouTube for recent videos matching seed queries, groups them by channel,
then checks each candidate channel's RSS feed to see how often it actually posts.
Read-only: prints a ranked report.
"""

import asyncio
import calendar
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

SEARCH = "https://www.googleapis.com/youtube/v3/search"
FEED = "https://www.youtube.com/feeds/videos.xml"
SEEDS = [
    "白嫖",
    "免费额度",
    "免费 API",
    "薅羊毛",
    "免费VPS",
    "免费服务器",
    "cloud credits",
    "free tier",
    "free API",
    "free GPU",
    "AI 额度",
    "学生优惠",
]
PERK_RE = re.compile(
    r"白嫖|免费|额度|赠金|试用|赠送|兑换|领取|优惠|学生|羊毛|"
    r"credits?|free|trial|giveaway|promo|redeem|discount|student",
    re.I,
)


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("YOUTUBE_API_KEY missing")
        return
    os.environ.pop("NO_PROXY", None)
    os.environ.pop("no_proxy", None)

    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    channels: dict[str, dict] = {}
    hits: Counter = Counter()
    titles: list[str] = []

    async with httpx.AsyncClient(timeout=40.0) as client:
        for seed in SEEDS:
            resp = await client.get(
                SEARCH,
                params={
                    "key": key,
                    "part": "snippet",
                    "type": "video",
                    "order": "relevance",
                    "maxResults": 25,
                    "q": seed,
                    "publishedAfter": since,
                    "relevanceLanguage": "zh-Hans" if re.search(r"[\u4e00-\u9fff]", seed) else "en",
                },
            )
            if resp.status_code != 200:
                print(f"[{seed}] HTTP {resp.status_code}: {resp.text[:120]}")
                continue
            items = (resp.json().get("items") or [])
            for item in items:
                snippet = item.get("snippet") or {}
                cid = snippet.get("channelId")
                title = snippet.get("title", "")
                if not cid:
                    continue
                hits[cid] += 1
                channels.setdefault(
                    cid,
                    {
                        "name": snippet.get("channelTitle", ""),
                        "titles": [],
                    },
                )["titles"].append(title)
                if PERK_RE.search(title):
                    titles.append(title)

        print(f"=== channels hit by {len(SEEDS)} seeds, top 15 ===")
        for cid, count in hits.most_common(15):
            info = channels[cid]
            feed = feedparser.parse(
                (await client.get(FEED, params={"channel_id": cid})).text
            )
            recent = [
                entry
                for entry in feed.entries
                if entry.get("published_parsed")
                and datetime.fromtimestamp(
                    calendar.timegm(entry.published_parsed), tz=timezone.utc
                )
                >= datetime.now(timezone.utc) - timedelta(hours=72)
            ]
            print(
                f"\n{count:2d} hits | 72h videos={len(recent):2d} | {info['name']} | {cid}"
            )
            for entry in recent[:3]:
                print(f"     - {entry.get('title', '')[:90]}")
            for title in info["titles"][:3]:
                print(f"     · {title[:90]}")

        print("\n=== perk-matching titles (for keyword mining) ===")
        for title in titles[:40]:
            print(f"  {title[:100]}")


if __name__ == "__main__":
    asyncio.run(main())