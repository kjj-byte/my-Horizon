"""Built-in tools available to enrichment blocks."""

import asyncio
from dataclasses import dataclass
from datetime import timezone
import logging
from pathlib import Path
from typing import Any

from ddgs import DDGS

from ..models import ContentItem
from .history import HistorySearchTool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResult:
    request_id: str
    block_id: str
    tool: str
    results: list[dict[str, str]]


class WebSearchTool:
    name = "web_search"

    # DuckDuckGo rate-limits silently (empty list) or errors; one retry plus a
    # second engine turns most CI misses into results.
    _BACKENDS: tuple[str | None, ...] = (None, "brave", "google")
    _RETRY_DELAY = 0.5

    async def execute(self, arguments: dict[str, Any]) -> list[dict[str, str]]:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("web_search requires a non-empty query")

        error: Exception | None = None
        for backend in self._BACKENDS:
            try:
                kwargs: dict[str, Any] = {"max_results": 3}
                if backend:
                    kwargs["backend"] = backend
                raw = await asyncio.to_thread(DDGS().text, query.strip(), **kwargs)
            except Exception as exc:  # includes ddgs "No results found"
                error = exc
                await asyncio.sleep(self._RETRY_DELAY)
                continue
            results = [
                {
                    "title": str(result.get("title", "")),
                    "url": str(result.get("href", "")),
                    "text": str(result.get("body", "")),
                }
                for result in (raw or [])
                if result.get("href")
            ]
            if results:
                return results
            error = None
            await asyncio.sleep(self._RETRY_DELAY)

        if error is not None:
            logger.warning("web_search failed for %r: %s", query, error)
        return []


class ToolRegistry:
    """Small allowlisted registry for executable profile tools."""

    def __init__(self, summaries_dir: Path | None = None):
        self._tools = {
            WebSearchTool.name: WebSearchTool(),
            HistorySearchTool.name: HistorySearchTool(summaries_dir),
        }

    @property
    def names(self) -> set[str]:
        return set(self._tools)

    async def execute(
        self,
        request_id: str,
        block_id: str,
        tool: str,
        arguments: dict[str, Any],
        current_item: ContentItem | None = None,
    ) -> ToolResult:
        try:
            implementation = self._tools[tool]
        except KeyError as exc:
            raise ValueError(f"Unknown enrichment tool: {tool}") from exc
        if isinstance(implementation, HistorySearchTool) and current_item is not None:
            results = await implementation.execute(
                arguments,
                before=current_item.published_at.astimezone(timezone.utc).date(),
                exclude_url=str(current_item.url),
            )
        else:
            results = await implementation.execute(arguments)
        return ToolResult(
            request_id=request_id,
            block_id=block_id,
            tool=tool,
            results=results,
        )
