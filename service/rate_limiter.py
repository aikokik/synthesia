import time

from redis.asyncio.client import Redis


class RateLimiter:
    def __init__(
        self,
        redis_client: Redis,
        limit: int = 10,
        window: int = 60,  # default arguments based on task description. todo(move such variables to configuration)
    ) -> None:
        self._redis_client = redis_client
        self._limit = limit
        self._window = window
        self._name = "rate_limiter"

    async def is_request_allowed(self, request_id: str) -> bool:
        # lets do for now general rate limiter not user based
        # for task simplicity. todo: can be extended to add granularity
        # f.e. per user
        now = time.time()
        window_start = now - self._window

        pipeline = self._redis_client.pipeline()
        pipeline.zremrangebyscore(self._name, 0, window_start)
        pipeline.zcard(self._name)
        _, current_count = await pipeline.execute()

        if current_count < self._limit:
            pipeline = self._redis_client.pipeline()
            pipeline.zadd(self._name, {request_id: now})
            pipeline.expire(self._name, self._window + 3)
            await pipeline.execute()
            return True
        else:
            return False
