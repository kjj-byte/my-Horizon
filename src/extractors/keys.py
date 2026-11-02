"""Ordered API keys with fallback on quota or rate-limit responses."""

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# 401/402: key has no budget; 429: this account's rate limit is exhausted.
ROTATE_STATUS = {401, 402, 429}


def key_envs(single: str, many: List[str]) -> List[str]:
    return list(many) or [single]


def load_keys(single: str, many: List[str]) -> List[str]:
    return [key for key in (os.getenv(name) for name in key_envs(single, many)) if key]


async def post_json(
    endpoint: str,
    payload: dict,
    keys: List[str],
    client: httpx.AsyncClient,
    timeout: float = 120.0,
) -> Optional[dict]:
    """POST with the first key that still has quota, rotating on 401/402/429."""
    for index, key in enumerate(keys):
        try:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            logger.warning("%s request failed: %s", endpoint, exc)
            return None
        if response.status_code in ROTATE_STATUS:
            logger.warning(
                "%s key #%d hit HTTP %d; trying the next key",
                endpoint,
                index + 1,
                response.status_code,
            )
            continue
        if response.status_code != 200:
            logger.warning("%s HTTP %d: %s", endpoint, response.status_code, response.text[:160])
            return None
        try:
            return response.json()
        except ValueError:
            logger.warning("%s returned invalid JSON", endpoint)
            return None
    return None