"""Firecrawl hosted scrape: page -> markdown.

Free plan: ~500 credits/month, one credit per page.
"""

import logging
from typing import Optional

import httpx

from .base import BaseExtractor
from .keys import load_keys, post_json
from ..models import FirecrawlExtractorConfig

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
TIMEOUT = 120.0


class FirecrawlExtractor(BaseExtractor):
    def __init__(self, config: FirecrawlExtractorConfig):
        self._config = config

    async def extract(self, url: str, client: httpx.AsyncClient) -> Optional[str]:
        keys = load_keys(self._config.api_key_env, self._config.api_key_envs)
        if not keys:
            logger.warning(
                "No key in %s; skipping Firecrawl extraction",
                [self._config.api_key_env, *self._config.api_key_envs],
            )
            return None

        body = await post_json(
            ENDPOINT, {"url": url, "formats": ["markdown"]}, keys, client, timeout=TIMEOUT
        )
        if not body:
            return None
        markdown = ((body.get("data") or {}).get("markdown") or "").strip()
        return markdown[: self._config.max_chars] or None