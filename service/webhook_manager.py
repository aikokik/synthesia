from typing import Any
import asyncio
import logging

import httpx


logger = logging.getLogger(__name__)


async def process_webhook(
    webhook_url: str,
    data: dict[str, Any],
    timeout: float = 10,
    max_retries: int = 3,
) -> None:
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(webhook_url, json=data, timeout=timeout)
                response.raise_for_status()
                logger.info(f"Webhook sent to {webhook_url}, status: {response.status_code}")
                return
            except Exception:
                # todo: update any monitoring metrics
                logger.exception(f"Error sending webhook to {webhook_url}.")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying webhook to {webhook_url} in {2**attempt} seconds")
                    await asyncio.sleep(2**attempt)
