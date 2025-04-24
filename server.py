from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncGenerator, Union
import asyncio
import logging
import uuid

from pydantic import HttpUrl
import fastapi
import redis.asyncio as redis

from configs.config import SynthesiaAPIConfig
from configs.logging import setup_logging
from service.queue import QueueProcessor, RequestProcessingQueue
from service.rate_limiter import RateLimiter
from service.service import CryptoSignResponse, Service
from upstream.synthesia_api import SynthesiaAPI
from utils.auth import get_auth_info
from utils.helpers import RequestHeaders, is_docker


setup_logging(log_level="DEBUG", log_dir="logs", app_name="booking_api")
logger = logging.getLogger(__name__)


class AppState:
    def __init__(self) -> None:
        self.service: Service | None = None
        self.config: SynthesiaAPIConfig | None = None
        self.redis_client: redis.Redis | None = None
        self.queue_processor_task: asyncio.Task | None = None
        self.rate_limiter: RateLimiter | None = None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Application startup")
    if not is_docker():
        raise EnvironmentError("This service must be run in a Docker container.")
    app_state.redis_client = await redis.from_url("redis://redis:6379")
    app_state.rate_limiter = RateLimiter(app_state.redis_client)
    queue = RequestProcessingQueue("sign_requests", app_state.redis_client)
    app_state.config = SynthesiaAPIConfig()
    upstream_api = SynthesiaAPI(app_state.config)
    app_state.service = Service(queue, upstream_api, app_state.rate_limiter)
    queue_processor = QueueProcessor(queue, upstream_api, app_state.rate_limiter)
    app_state.queue_processor_task = asyncio.create_task(queue_processor.process())

    yield

    logger.info("Application shutdown")
    if app_state.queue_processor_task:
        await app_state.queue_processor_task.cancel()
        try:
            await app_state.queue_processor_task
        except asyncio.CancelledError:
            logger.info("Queue processor task cancelled")
        except Exception as e:
            logger.exception(f"Error while cancelling queue processor: {e}")
    if app_state.redis_client:
        await app_state.redis_client.close()


app = fastapi.FastAPI(
    title="Synthesia Crypto Signing API",
    description="Wrapper for Synthesia signing requests",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "Reliable Crypto Signing API",
        "status": "operational",
        "endpoints": ["/crypto/sign"],
    }


@app.get(
    "/crypto/sign",
    response_model=CryptoSignResponse,
    description="Sign a message with a secret RSA key",
)
async def sign_message(
    message: Annotated[str, fastapi.Query(description="Message to sign")],
    background_tasks: fastapi.BackgroundTasks,
    authorization: Annotated[str, fastapi.Header(description="API Key")],
    webhook_url: Annotated[
        Union[HttpUrl, None],
        fastapi.Query(description="URL to notify when signature is ready"),
    ] = None,
) -> CryptoSignResponse:
    if not app_state.service or not app_state.config:
        raise fastapi.HTTPException(
            status_code=500,
            detail="Service not initialized",
        )

    auth_info = get_auth_info(authorization, app_state.config)
    request_id = str(uuid.uuid4())
    request_headers = RequestHeaders(user_id=auth_info.user_id, request_id=request_id)
    logger.info(f"Processing request {request_id} for user {auth_info.user_id}")
    return await app_state.service.sign_message(
        request_headers=request_headers,
        message=message,
        background_tasks=background_tasks,
        webhook_url=webhook_url,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
