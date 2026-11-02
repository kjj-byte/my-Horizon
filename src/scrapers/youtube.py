"""YouTube Data API v3 search source."""

import logging
import os
import re
from datetime import datetime, timezone
from typing import List

import httpx

from .base import BaseScraper
from ..models import (
    ContentItem,
    SourceType,
    YouTubeConfig,
    YouTubeQueryConfig,
)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
MAX_ERROR_CHARS = 300
IDS_PER_REQUEST = 50

logger = logging.getLogger(__name__)


class YouTubeScraper(BaseScraper):
    """Fetch videos uploaded since the window start, ordered by upload date."""

    def __init__(self, config: YouTubeConfig, http_client: httpx.AsyncClient):
        super().__init__(config.model_dump(), http_client)
        self.youtube_config = config

    async def fetch(self, since: datetime) -> List[ContentItem]:
        if not self.config.get("enabled", True):
            return []

        api_key = os.getenv(self.youtube_config.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.youtube_config.api_key_env} is not set; "
                "add it as an Actions secret and map it in the workflow env"
            )

        items: List[ContentItem] = []
        seen = set()
        for query_config in self.youtube_config.queries:
            if not query_config.enabled:
                continue
            for item in await self._search(query_config, api_key, since):
                if item.id in seen:
                    continue
                seen.add(item.id)
                items.append(item)

        if self.youtube_config.max_items:
            items.sort(key=lambda item: item.published_at, reverse=True)
            items = items[: self.youtube_config.max_items]
        return await self._enrich(items, api_key)

    async def _enrich(self, items: List[ContentItem], api_key: str) -> List[ContentItem]:
        """Fill full descriptions, duration and stats; search snippets are truncated."""
        by_id = {
            item.metadata.get("video_id"): item
            for item in items
            if item.metadata.get("video_id")
        }
        video_ids = list(by_id)
        for start in range(0, len(video_ids), IDS_PER_REQUEST):
            chunk = video_ids[start : start + IDS_PER_REQUEST]
            params = {
                "key": api_key,
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(chunk),
                "maxResults": IDS_PER_REQUEST,
            }
            try:
                response = await self.client.get(VIDEOS_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                # Search results are still usable without the extra details.
                logger.warning("YouTube videos.list enrichment failed: %s", exc)
                return items

            for entry in payload.get("items") or []:
                video_id = entry.get("id")
                if not isinstance(video_id, str):
                    continue
                item = by_id.get(video_id)
                if item is None:
                    continue
                snippet = entry.get("snippet") or {}
                if snippet.get("description"):
                    item.content = snippet["description"].strip() or item.content
                details = entry.get("contentDetails") or {}
                stats = entry.get("statistics") or {}
                item.metadata["duration"] = details.get("duration")
                item.metadata["view_count"] = stats.get("viewCount")
                item.metadata["like_count"] = stats.get("likeCount")
                suffix = _enrichment_suffix(details.get("duration"), stats.get("viewCount"))
                if suffix:
                    # Prefix survives the analysis prefix-sampling budget.
                    item.content = suffix + (item.content or "").lstrip()
        return items

    async def _search(
        self,
        query_config: YouTubeQueryConfig,
        api_key: str,
        since: datetime,
    ) -> List[ContentItem]:
        params: dict[str, str | int] = {
            "key": api_key,
            "part": "snippet",
            "type": "video",
            "order": "date",
            "maxResults": self.youtube_config.max_results,
            "q": query_config.query,
            "publishedAfter": since.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        if query_config.language:
            params["relevanceLanguage"] = query_config.language
        if query_config.region:
            params["regionCode"] = query_config.region

        response = await self.client.get(SEARCH_URL, params=params)
        if response.status_code in (400, 403):
            raise RuntimeError(
                f"YouTube API rejected query {query_config.query!r} "
                f"(HTTP {response.status_code}): {_error_message(response)}"
            )
        response.raise_for_status()
        return self._parse(response.json(), query_config, since)

    def _parse(
        self,
        payload: dict,
        query_config: YouTubeQueryConfig,
        since: datetime,
    ) -> List[ContentItem]:
        items: List[ContentItem] = []
        for entry in payload.get("items") or []:
            video_id = (entry.get("id") or {}).get("videoId")
            snippet = entry.get("snippet") or {}
            if not video_id or not snippet.get("publishedAt"):
                continue
            published_at = _parse_timestamp(snippet["publishedAt"])
            if published_at is None or published_at < since:
                continue
            items.append(
                ContentItem(
                    id=self._generate_id(SourceType.YOUTUBE.value, "search", video_id),
                    source_type=SourceType.YOUTUBE,
                    title=snippet.get("title") or video_id,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    content=snippet.get("description") or None,
                    author=snippet.get("channelTitle"),
                    published_at=published_at,
                    profile=self.youtube_config.profile,
                    metadata={
                        "yt_query": query_config.query,
                        "video_id": video_id,
                        "channel_id": snippet.get("channelId"),
                        "category": self.youtube_config.category,
                    },
                )
            )
        return items


def _parse_timestamp(value: str):
    """Parse an RFC 3339 timestamp from the API."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def _duration_text(value) -> str:
    """Format an ISO 8601 duration as H:MM:SS / M:SS."""
    match = _DURATION_RE.match(str(value or ""))
    if not match:
        return ""
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _enrichment_suffix(duration, view_count) -> str:
    """One-line metadata header for the model: duration and views."""
    parts = []
    text = _duration_text(duration)
    if text:
        parts.append(f"时长 {text}")
    try:
        views = int(view_count)
    except (TypeError, ValueError):
        views = None
    if views is not None:
        parts.append(f"播放 {views:,}")
    if not parts:
        return ""
    return f"[{' · '.join(parts)}]\n\n"


def _error_message(response: httpx.Response) -> str:
    """Extract Google's error message without assuming a body shape."""
    try:
        error = (response.json().get("error") or {}).get("message") or ""
    except ValueError:
        error = response.text
    return str(error).strip()[:MAX_ERROR_CHARS] or "no message"