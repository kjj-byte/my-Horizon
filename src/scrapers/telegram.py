"""Telegram public channel scraper implementation."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import ContentItem, TelegramConfig, TelegramChannelConfig, SourceType

logger = logging.getLogger(__name__)

TELEGRAM_WEB_BASES = (
    "https://telegram.me/s",
    "https://telegram.dog/s",
    "https://t.me/s",
)
TELEGRAM_LINK_BASE = "https://telegram.me"
USER_AGENT = "Mozilla/5.0 (compatible; Horizon/1.0; +https://github.com/thysrael/horizon)"
# One preview page holds ~20 messages; follow ?before= a few pages back so a
# busy channel can fill a fetch_limit above 20.
MAX_PAGES = 4
MIN_PAGE_MESSAGES = 5


class TelegramScraper(BaseScraper):
    """Scraper for Telegram public channels via web preview."""

    def __init__(self, config: TelegramConfig, http_client: httpx.AsyncClient):
        super().__init__(config.model_dump(), http_client)
        self.telegram_config = config

    async def fetch(self, since: datetime) -> List[ContentItem]:
        if not self.config.get("enabled", True):
            return []

        tasks = []
        for channel_cfg in self.telegram_config.channels:
            if channel_cfg.enabled:
                tasks.append(self._fetch_channel(channel_cfg, since))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        items = []
        failures = []
        for result in results:
            if isinstance(result, Exception):
                failures.append(result)
                logger.warning("Error fetching Telegram channel: %s", result)
            elif isinstance(result, list):
                items.extend(result)

        if failures and len(failures) == len(results):
            raise RuntimeError(f"All Telegram channels failed: {failures[0]}") from failures[0]
        return items

    async def _fetch_channel(self, cfg: TelegramChannelConfig, since: datetime) -> List[ContentItem]:
        headers = {"User-Agent": USER_AGENT}
        items: List[ContentItem] = []
        seen: set[str] = set()
        before = ""

        for _ in range(MAX_PAGES):
            html = await self._get_channel_page(cfg.channel, before, headers)
            soup = BeautifulSoup(html, "html.parser")
            messages = soup.select("div.tgme_widget_message[data-post]")
            if not messages:
                break

            page_items = self._parse_channel_html(html, cfg, since)
            new_items = [item for item in page_items if item.id not in seen]
            seen.update(item.id for item in new_items)
            items.extend(new_items)

            # A short page means the channel has no older history to follow,
            # even when the page is not yet full of in-window messages.
            oldest = self._oldest_message(messages[0])
            if (
                len(items) >= cfg.fetch_limit
                or len(messages) < MIN_PAGE_MESSAGES
                or oldest is None
                or oldest[1] < since
                or not new_items
            ):
                break
            before = oldest[0]

        return items[: cfg.fetch_limit]

    async def _get_channel_page(self, channel: str, before: str, headers: dict) -> str:
        """Fetch one preview page, trying each Telegram web domain in turn."""
        failures = []
        for web_base in TELEGRAM_WEB_BASES:
            url = f"{web_base}/{channel}"
            if before:
                url += f"?before={before}"
            try:
                response = await self.client.get(url, headers=headers, follow_redirects=True, timeout=120.0)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning("Telegram rate limited for %s, retrying after %ds", channel, retry_after)
                    await asyncio.sleep(retry_after)
                    response = await self.client.get(url, headers=headers, follow_redirects=True, timeout=120.0)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                failures.append(exc)
                logger.warning(
                    "Telegram request failed for %s via %s: [%s] %r",
                    channel,
                    web_base,
                    type(exc).__name__,
                    exc,
                )

        last_failure = failures[-1]
        raise RuntimeError(
            f"All Telegram endpoints failed for {channel}: "
            f"{type(last_failure).__name__}: {last_failure}"
        ) from last_failure

    @staticmethod
    def _oldest_message(msg_el) -> Optional[tuple[str, datetime]]:
        """Return (message id, published_at) for the oldest message on a page."""
        data_post = msg_el.get("data-post", "")
        msg_id = data_post.split("/")[-1] if "/" in data_post else data_post
        time_el = msg_el.select_one("time[datetime]")
        if not msg_id or not time_el:
            return None
        try:
            return msg_id, datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            return None

    def _parse_channel_html(
        self, html: str, cfg: TelegramChannelConfig, since: datetime
    ) -> List[ContentItem]:
        soup = BeautifulSoup(html, "html.parser")
        messages = soup.select("div.tgme_widget_message[data-post]")

        items = []
        for msg in messages[-cfg.fetch_limit:]:
            item = self._parse_message(msg, cfg, since)
            if item:
                items.append(item)
        return items

    def _parse_message(
        self, msg_el, cfg: TelegramChannelConfig, since: datetime
    ) -> Optional[ContentItem]:
        channel = cfg.channel
        # Extract message ID
        data_post = msg_el.get("data-post", "")
        msg_id = data_post.split("/")[-1] if "/" in data_post else data_post
        if not msg_id:
            return None

        # Extract timestamp
        time_el = msg_el.select_one("time[datetime]")
        if not time_el:
            return None
        try:
            published_at = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            return None

        if published_at < since:
            return None

        # Extract message text
        text_el = msg_el.select_one("div.tgme_widget_message_text.js-message_text")
        if not text_el:
            return None

        # Convert <br> to newlines, then strip tags
        for br in text_el.find_all("br"):
            br.replace_with("\n")
        raw_text = text_el.get_text(separator="")
        text = raw_text.strip()

        if not text:
            return None

        if cfg.filter_keywords and not any(
            keyword.casefold() in text.casefold() for keyword in cfg.filter_keywords
        ):
            return None

        # Generate title from first paragraph
        title = self._make_title(text)

        # Find first external link as canonical URL; fallback to message URL
        msg_url = f"{TELEGRAM_LINK_BASE}/{channel}/{msg_id}"
        canonical_url = msg_url
        for a in text_el.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "t.me" not in href:
                canonical_url = href
                break

        item_fields = dict(
            id=self._generate_id("telegram", channel, msg_id),
            source_type=SourceType.TELEGRAM,
            title=title,
            content=text,
            author=channel,
            published_at=published_at,
            profile=cfg.profile,
            metadata={"msg_url": msg_url, "channel": channel, "category": cfg.category},
        )
        # Percent-encoded IDN links are rejected by the URL type; keep the post
        # with its Telegram permalink instead of dropping the channel's batch.
        for url in (canonical_url, msg_url):
            try:
                return ContentItem(url=url, **item_fields)
            except ValueError:
                continue
        return None

    @staticmethod
    def _make_title(text: str) -> str:
        # Take first paragraph (split on double newline)
        first_para = text.split("\n\n")[0].replace("\n", " ").strip()

        if len(first_para) <= 80:
            return first_para

        # Try to break at a Chinese sentence-ending punctuation within first 80 chars
        match = re.search(r"[。！？]", first_para[:80])
        if match:
            return first_para[: match.end()]

        # Fallback: hard truncate
        return first_para[:80]
