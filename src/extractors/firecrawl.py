"""Firecrawl hosted scrape: page -> markdown.

Free plan: ~500 credits/month, one credit per page.
"""

import logging
import os
from typing import Optional

import httpx

from .base import BaseExtractor
from ..models import FirecrawlExtractorConfig

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
TIMEOUT = 120.0


class FirecrawlExtractor(BaseExtractor):
    def __init__(self, config: FirecrawlExtractorConfig):
        self._config = config

    async def extract(self, url: str, client: httpx.AsyncClient) -> Optional[str]:
        key = os.getenv(self._config.api_key_env)
        if not key:
            logger.warning("%s is not set; skipping Firecrawl extraction", self._config.api_key_env)
            return None

        try:
            response = await client.post(
                ENDPOINT,
                json={"url": url, "formats": ["markdown"]},
                headers={"Authorization": f"Bearer {key}"},
                timeout=TIMEOUT,
            )
            if response.status_code != 200:
                logger.warning("Firecrawl HTTP %s for %s: %s", response.status_code, url, response.text[:160])
                return None
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Firecrawl extraction failed for %s: %s", url, exc)
            return None

        markdown = ((body.get("data") or {}).get("markdown") or "").strip()
        return markdown[: self._config.max_chars] or None