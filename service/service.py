import logging
import time

from fastapi import BackgroundTasks
from pydantic import HttpUrl
import fastapi

from service.models import CryptoSignResponse
from service.queue import RequestMetadata, RequestProcessingQueue, SignRequest
from service.rate_limiter import RateLimiter
from service.webhook_manager import process_webhook
from upstream.synthesia_api import SynthesiaAPI, SynthesiaSignRequest
from utils.helpers import RequestHeaders


logger = logging.getLogger(__name__)


class Service:
    def __init__(
        self,
        queue: RequestProcessingQueue,
        upstream_api: SynthesiaAPI,
        rate_limiter: RateLimiter,
    ) -> None:
        self._queue = queue
        self._upstream_api = upstream_api
        self._rate_limiter = rate_limiter
        # simple cache for illustrative purposes, production should use # Redis or something similar
        self._cache: dict[str, tuple[CryptoSignResponse, float]] = {}

    async def sign_message(
        self,
        request_headers: RequestHeaders,
        message: str,
        background_tasks: BackgroundTasks,
        webhook_url: HttpUrl | None,
    ) -> CryptoSignResponse | None:
        logger.info(f"Signing message: {message}")
        if message in self._cache:
            response, timestamp = self._cache[message]
            if time.time() - timestamp < 180:  # 3 minutes hardcoded for simplicity
                logger.info(f"Returning cached response for message: {message}")
                if webhook_url is not None:
                    logger.info(f"Notifying webhook {webhook_url}")
                    background_tasks.add_task(
                        process_webhook,
                        webhook_url=str(webhook_url),
                        data=response.model_dump(),
                    )
                return response
            else:
                logger.info(f"Removing cached response for message: {message} as expired")
                del self._cache[message]
        request_allowed = await self._rate_limiter.is_request_allowed(request_headers.request_id)
        if not request_allowed and webhook_url is None:
            logger.error(
                f"Request {request_headers.request_id} is rate limited."
                f"No webhook URL provided. Returning too many requests response."
            )
            return CryptoSignResponse(
                request_id=request_headers.request_id,
                status=fastapi.status.HTTP_429_TOO_MANY_REQUESTS,
                message="Too many requests. Please provide webhook URL "
                "to receive a response when the signature is ready.",
            )
        if request_allowed:
            try:
                result = await self._upstream_api.sign_message(SynthesiaSignRequest(message=message))
                response = CryptoSignResponse(
                    request_id=request_headers.request_id,
                    status=fastapi.status.HTTP_200_OK,
                    signature=result.signature,
                )
                if webhook_url is not None:
                    logger.info(f"Notifying webhook {webhook_url}")
                    background_tasks.add_task(
                        process_webhook,
                        webhook_url=str(webhook_url),
                        data=response.model_dump(),
                    )
                self._cache[message] = (response, time.time())
                return response
            except Exception as e:
                logger.exception(f"Error signing message: {e}")

        if webhook_url is None:
            logger.error(
                f"Request {request_headers.request_id} failed.No webhook URL provided. Returning error response."
            )
            return CryptoSignResponse(
                request_id=request_headers.request_id,
                status=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Error signing message.",
            )
        enqueued_time = time.time()
        try:
            # add to queue only if webhook_url is provided
            logger.info(f"Adding request {request_headers.request_id} to queue.")
            await self._queue.add(
                SignRequest(
                    message=message,
                    webhook_url=webhook_url,
                    metadata=RequestMetadata(
                        request_id=request_headers.request_id,
                        created_at=enqueued_time,
                        retries=0,
                        updated_at=enqueued_time,
                    ),
                ),
            )
            return CryptoSignResponse(
                request_id=request_headers.request_id,
                status=fastapi.status.HTTP_202_ACCEPTED,
                message="Your request is being processed asynchronously.",
            )
        except Exception as queue_error:
            logger.error(f"Failed to queue request: {queue_error}")
            return CryptoSignResponse(
                request_id=request_headers.request_id,
                status=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Error processing your request.",
            )
