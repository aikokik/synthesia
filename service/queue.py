from collections import deque
from typing import TypedDict
import asyncio
import json
import logging
import time

from fastapi import status
from pydantic import HttpUrl
from redis.asyncio.client import Redis

from service.models import CryptoSignResponse
from service.rate_limiter import RateLimiter
from service.webhook_manager import process_webhook
from upstream.synthesia_api import SynthesiaAPI, SynthesiaSignRequest


logger = logging.getLogger(__name__)


class RequestMetadata(TypedDict):
    request_id: str
    created_at: float
    retries: int
    updated_at: float


class SignRequest(TypedDict):
    message: str
    webhook_url: HttpUrl
    metadata: RequestMetadata


class RequestProcessingQueue:
    def __init__(self, name: str, redis_client: Redis) -> None:
        self.name = name
        self._redis_client = redis_client

    async def add(self, request: SignRequest) -> None:
        request_id = request["metadata"]["request_id"]
        request["webhook_url"] = str(request["webhook_url"])
        await self._redis_client.hset(
            f"request:{request_id}",
            mapping={"data": json.dumps(request)},
        )
        await self._redis_client.zadd(self.name, {request_id: request["metadata"]["updated_at"]})

    async def get(self) -> list[SignRequest] | None:
        # get the request within the current time window
        now = time.time()
        next_requests = await self._redis_client.zrangebyscore(self.name, 0, now)
        logger.info(f"Found {next_requests} requests in queue")
        if not next_requests:
            return None
        result = []
        for next_request in next_requests:
            logger.info(f"Processing request from Redis: {next_request}")
            if isinstance(next_request, bytes):
                request_id = next_request.decode("utf-8")
            else:
                request_id = str(next_request)
            request_data = await self._redis_client.hget(f"request:{request_id}", "data")
            if request_data:
                request_dict = json.loads(request_data)
                request_dict["webhook_url"] = HttpUrl(request_dict["webhook_url"])
                result.append(SignRequest(**request_dict))
        return result if result else None

    async def remove(self, request_id: str) -> None:
        await self._redis_client.delete(f"request:{request_id}")
        await self._redis_client.zrem(self.name, request_id)


class QueueProcessor:
    def __init__(
        self,
        queue: RequestProcessingQueue,
        upstream_api: SynthesiaAPI,
        rate_limiter: RateLimiter,
        upstream_api_max_retries: int = 3,
    ) -> None:
        self._queue = queue
        self._upstream_api = upstream_api
        self._upstream_api_max_retries = upstream_api_max_retries
        self._rate_limiter = rate_limiter

    async def process(self) -> None:
        logger.info(f"Starting queue processor for queue {self._queue.name}")
        try:
            while True:
                try:
                    next_requests = await self._queue.get()
                    if next_requests is None:
                        logger.info(f"No requests found in queue {self._queue.name}, sleeping for 10 seconds")
                        await asyncio.sleep(10)
                        continue
                    logger.info(f"Processing {len(next_requests)} requests from queue {self._queue.name}")
                    # hack: convert list to queue to handle rate limiting
                    next_requests = deque(next_requests)
                    while next_requests:
                        next_request = next_requests[0]
                        is_request_allowed = await self._rate_limiter.is_request_allowed(
                            next_request["metadata"]["request_id"]
                        )
                        if not is_request_allowed:
                            logger.info("Upstream API is rate limited, sleeping for 10 seconds")
                            await asyncio.sleep(10)
                            continue
                        next_requests.popleft()
                        await self._process_request(next_request)
                except Exception as e:
                    logger.exception(f"Error in queue processor main loop: {e}")
                    await asyncio.sleep(10)  # Sleep before retrying to prevent tight error loop
        except asyncio.CancelledError:
            logger.info("Queue processor cancelled")
            raise
        except Exception as e:
            logger.exception(f"Fatal error in queue processor: {e}")
            raise

    async def _process_request(self, next_request: SignRequest) -> None:
        logger.info(f"Processing next request {next_request['metadata']['request_id']} from queue {self._queue.name}")
        if next_request["webhook_url"] is None:
            # avoid processing requests without webhook URL
            logger.warning(f"Request {next_request['metadata']['request_id']} has no webhook URL, skipping")
            await self._queue.remove(next_request["metadata"]["request_id"])
            return
        try:
            result = await self._upstream_api.sign_message(SynthesiaSignRequest(message=next_request["message"]))
            response = CryptoSignResponse(
                request_id=next_request["metadata"]["request_id"],
                status=status.HTTP_200_OK,
                signature=result.signature,
            )
            await process_webhook(
                webhook_url=str(next_request["webhook_url"]),
                data=response.model_dump(),
            )
            await self._queue.remove(next_request["metadata"]["request_id"])
        except Exception as e:
            logger.exception(f"Error processing request {next_request['metadata']['request_id']}: {e}")
            if next_request["metadata"]["retries"] >= self._upstream_api_max_retries:
                logger.info(
                    f"Request {next_request['metadata']['request_id']} failed after "
                    f"{self._upstream_api_max_retries} retries, giving up"
                )
                await self._queue.remove(next_request["metadata"]["request_id"])
                await process_webhook(
                    webhook_url=str(next_request["webhook_url"]),
                    data=CryptoSignResponse(
                        request_id=next_request["metadata"]["request_id"],
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        message="Error signing message.",
                    ).model_dump(),
                )
            else:
                # retry with exponential backoff
                retries = next_request["metadata"]["retries"] + 1
                backoff = min(180, 30 * (2**retries))  # max of 3 minutes
                next_attempt = time.time() + backoff
                logger.info(
                    f"Adding request {next_request['metadata']['request_id']} to queue "
                    f"to retry with exponential backoff {backoff} seconds"
                )
                await self._queue.add(
                    SignRequest(
                        message=next_request["message"],
                        webhook_url=next_request["webhook_url"],
                        metadata=RequestMetadata(
                            request_id=next_request["metadata"]["request_id"],
                            created_at=next_request["metadata"]["created_at"],
                            retries=retries,
                            updated_at=next_attempt,
                        ),
                    )
                )
