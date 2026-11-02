"""Listing pages turned into items through Crawl4AI's /extract endpoint.

For sites without RSS (deal aggregators, forums, social search pages). Each
configured page costs credits, so this stays opt-in per site.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urljoin

import httpx

from .base import BaseScraper
from ..extractors.keys import load_keys, post_json
from ..models import ContentItem, SourceType, WebListConfig

logger = logging.getLogger(__name__)

EXTRACT_ENDPOINT = "https://api.crawl4ai.com/extract"
TIMEOUT = 180.0
SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "date": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["title", "url"],
    },
}


class WebListScraper(BaseScraper):
    def __init__(self, configs: List[WebListConfig], http_client: httpx.AsyncClient):
        super().__init__({}, http_client)
        self.web_lists = configs

    async def fetch(self, since: datetime) -> List[ContentItem]:
        items: List[ContentItem] = []
        seen: set[str] = set()
        for cfg in self.web_lists:
            if not cfg.enabled:
                continue
            for item in await self._fetch_list(cfg, since):
                if item.id not in seen:
                    seen.add(item.id)
                    items.append(item)
        return items

    async def _fetch_list(self, cfg: WebListConfig, since: datetime) -> List[ContentItem]:
        keys = load_keys(cfg.api_key_env, cfg.api_key_envs)
        if not keys:
            logger.warning(
                "No Crawl4AI key in %s; skipping %s",
                [cfg.api_key_env, *cfg.api_key_envs],
                cfg.name,
            )
            return []

        body = await post_json(
            EXTRACT_ENDPOINT,
            {"url": str(cfg.url), "instruction": cfg.instruction, "schema": SCHEMA},
            keys,
            self.client,
            timeout=TIMEOUT,
        )
        if not body:
            return []

        rows = body.get("data") or []
        items = []
        for row in rows[: cfg.max_items]:
            item = self._to_item(row, cfg, since)
            if item is not None:
                items.append(item)
        logger.info("%s: %d/%d rows kept", cfg.name, len(items), len(rows))
        return items

    def _to_item(
        self, row: dict, cfg: WebListConfig, since: datetime
    ) -> Optional[ContentItem]:
        if not isinstance(row, dict):
            return None
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        if not title or not url:
            return None
        url = urljoin(str(cfg.url), url)
        if not url.startswith("http"):
            return None

        published_at = self._parse_date(row.get("date")) or datetime.now(timezone.utc)
        if published_at < since:
            return None

        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return ContentItem(
            id=self._generate_id(SourceType.WEBLIST.value, "page", digest),
            source_type=SourceType.WEBLIST,
            title=title[:200],
            url=url,
            content=(str(row.get("summary") or "").strip() or None),
            author=cfg.name,
            published_at=published_at,
            profile=cfg.profile,
            metadata={
                "source_name": cfg.name,
                "web_list": cfg.name,
                "category": cfg.category,
            },
        )

    @staticmethod
    def _parse_date(value: object) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                parsed = datetime.fromisoformat(candidate)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        return None