"""Per-source fetch counts for the current config. Fetch only: no scoring, no docs."""

import asyncio
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from src.models import Config
from src.orchestrator import HorizonOrchestrator
from src.storage.manager import StorageManager

YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"
# Candidate search queries for the "free tier / API credits" beat.
YOUTUBE_QUERIES = [
    ("free tier cloud", "en"),
    ("free credits", "en"),
    ("free API key", "en"),
    ("free GPU", "en"),
    ("startup credits", "en"),
    ("免费额度 云", "zh"),
    ("白嫖 API", "zh"),
    ("免费 API", "zh"),
]


async def youtube_candidates() -> None:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("YOUTUBE_API_KEY missing")
        return
    since = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        for query, lang in YOUTUBE_QUERIES:
            params = {
                "key": key,
                "part": "snippet",
                "type": "video",
                "order": "date",
                "maxResults": 10,
                "q": query,
                "publishedAfter": since,
                "relevanceLanguage": lang,
            }
            resp = await client.get(YOUTUBE_SEARCH, params=params)
            if resp.status_code != 200:
                print(f"{query!r} HTTP {resp.status_code}: {resp.text[:160]}")
                continue
            data = resp.json()
            items = data.get("items") or []
            total = (data.get("pageInfo") or {}).get("totalResults", 0)
            print(f"{total:5d} total / {len(items):2d} recent  {query}")
            for entry in items[:5]:
                snippet = entry.get("snippet") or {}
                print(
                    f"   - {snippet.get('title', '')[:80]} | "
                    f"{snippet.get('channelTitle', '')[:28]}"
                )


async def main() -> None:
    if os.environ.get("PROBE_YOUTUBE") == "1":
        await youtube_candidates()
        return
    config = Config.model_validate(
        json.loads(Path("data/config.github.json").read_text(encoding="utf-8"))
    )
    if os.environ.get("PROBE_REDDIT") == "1":
        config.sources.reddit.enabled = True
    orchestrator = HorizonOrchestrator(config, StorageManager(Path("data")))
    since = orchestrator._determine_time_window()
    print(f"window_hours={config.collection.time_window_hours} since={since.isoformat()}")

    items = await orchestrator.fetch_all_sources(since)
    report = orchestrator.last_fetch_report
    print("=== per source: status, items, error ===")
    for outcome in report.outcomes:
        print(
            f"{outcome.source_name}\t{outcome.status}\t{len(outcome.items)}\t"
            f"{outcome.error or ''}"
        )

    print("=== per sub-source: items, source ===")
    counts = Counter(
        f"{item.source_type.value} / {orchestrator._sub_source_label(item)}"
        for item in items
    )
    for label, count in counts.most_common():
        print(f"{count}\t{label}")
    print(f"total_raw={len(items)}")


if __name__ == "__main__":
    asyncio.run(main())