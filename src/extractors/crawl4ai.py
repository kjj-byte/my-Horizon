"""Crawl4AI hosted scrape endpoint: page -> markdown.

Free plan: 1,000 credits/month, one credit per page, 10 requests/minute.
"""

import logging
from typing import Optional

import httpx

from .base import BaseExtractor
from .keys import load_keys, post_json
from ..models import Crawl4AIExtractorConfig

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.crawl4ai.com/scrape"
TIMEOUT = 120.0  # a page that needs a real browser can take up to 90s


class Crawl4AIExtractor(BaseExtractor):
    def __init__(self, config: Crawl4AIExtractorConfig):
        self._config = config

    async def extract(self, url: str, client: httpx.AsyncClient) -> Optional[str]:
        keys = load_keys(self._config.api_key_env, self._config.api_key_envs)
        if not keys:
            logger.warning(
                "No key in %s; skipping Crawl4AI extraction",
                [self._config.api_key_env, *self._config.api_key_envs],
            )
            return None

        body = await post_json(
            ENDPOINT, {"url": url, "format": "md"}, keys, client, timeout=TIMEOUT
        )
        if not body:
            return None
        markdown = (body.get("markdown") or "").strip()
        return markdown[: self._config.max_chars] or None