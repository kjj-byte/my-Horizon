"""One-off probe for the Apify Twitter source.

Separates the two ways the source can end up with 0 items: the actor returned an
empty dataset, or rows came back but `_parse_item` dropped them all.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from src.models import Config
from src.scrapers.twitter import TwitterScraper


async def main() -> None:
    config = Config.model_validate(
        json.loads(Path("data/config.github.json").read_text(encoding="utf-8"))
    )
    tw = config.sources.twitter
    print(f"actor={tw.actor_id} keywords={len(tw.keywords)}")
    print(f"actor_input={json.dumps(tw.actor_input, ensure_ascii=False)}")

    token = os.environ.get(tw.apify_token_env)
    print(f"token_present={bool(token)}")
    if not token:
        return

    since = datetime.now(timezone.utc) - timedelta(hours=72)
    async with httpx.AsyncClient(timeout=30.0) as client:
        scraper = TwitterScraper(tw, client)

        items = await scraper.fetch(since)
        print(f"fetch_items={len(items)}")
        terms = [keyword.casefold() for keyword in tw.keywords]
        matched = sum(
            1
            for item in items
            if any(
                term in f"{item.title} {item.content or ''}".casefold()
                for term in terms
            )
        )
        print(f"keyword_match={matched}/{len(items)}")
        for item in items[:8]:
            print(f"  sample: {item.title[:80]} | {item.published_at.isoformat()}")

        # Walk one raw dataset per keyword so "empty dataset" and "parser dropped
        # everything" cannot be confused again.
        for keyword in tw.keywords[:2]:
            payload = scraper._build_keyword_payload(keyword, 100)
            try:
                run_id, dataset_id = await scraper._start_run_with_payload(
                    token, payload
                )
            except Exception as exc:
                print(f"[{keyword}] start failed: {exc}")
                continue
            if not run_id or not dataset_id:
                print(f"[{keyword}] start failed")
                continue
            ok = await scraper._wait_for_run(token, run_id)
            rows = await scraper._fetch_dataset(token, dataset_id) if ok else []
            print(f"[{keyword}] ok={ok} rows={len(rows)}")
            if not rows:
                continue
            print(f"  keys={sorted(rows[0].keys())[:24]}")
            parsed = sum(
                1
                for row in rows
                if isinstance(row, dict) and scraper._parse_item(row, since)
            )
            print(f"  parsed={parsed}")
            print(f"  row0={json.dumps(rows[0], ensure_ascii=False)[:400]}")


if __name__ == "__main__":
    asyncio.run(main())