"""Per-source fetch counts for the current config. Fetch only: no scoring, no docs."""

import asyncio
import json
from collections import Counter
from pathlib import Path

from src.models import Config
from src.orchestrator import HorizonOrchestrator
from src.storage.manager import StorageManager


async def main() -> None:
    config = Config.model_validate(
        json.loads(Path("data/config.github.json").read_text(encoding="utf-8"))
    )
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