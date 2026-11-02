"""Crawl4AI hosted scrape endpoint: page -> markdown.

Free plan: 1,000 credits/month, one credit per page, 10 requests/minute.
"""

import logging
import os
from typing import Optional

import httpx

from .base import BaseExtractor
from ..models import Crawl4AIExtractorConfig

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.crawl4ai.com/scrape"
TIMEOUT = 120.0  # a page that needs a real browser can take up to 90s


class Crawl4AIExtractor(BaseExtractor):
    def __init__(self, config: Crawl4AIExtractorConfig):
        self._config = config

    async def extract(self, url: str, client: httpx.AsyncClient) -> Optional[str]:
        key = os.getenv(self._config.api_key_env)
        if not key:
            logger.warning("%s is not set; skipping Crawl4AI extraction", self._config.api_key_env)
            return None

        try:
            response = await client.post(
                ENDPOINT,
                json={"url": url, "format": "md"},
                headers={"Authorization": f"Bearer {key}"},
                timeout=TIMEOUT,
            )
            if response.status_code != 200:
                logger.warning("Crawl4AI HTTP %s for %s: %s", response.status_code, url, response.text[:160])
                return None
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Crawl4AI extraction failed for %s: %s", url, exc)
            return None

        markdown = (body.get("markdown") or "").strip()
        return markdown[: self._config.max_chars] or None