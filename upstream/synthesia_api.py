from logging import getLogger
import asyncio

from pydantic import BaseModel
import httpx

from configs.config import SynthesiaAPIConfig


logger = getLogger(__name__)


class SynthesiaSignRequest(BaseModel):
    message: str


class SynthesiaSignResponse(BaseModel):
    signature: str


class SynthesiaAPI:
    def __init__(self, config: SynthesiaAPIConfig) -> None:
        self._config = config
        self._headers = {"Authorization": self._config.api_key}

    async def sign_message(self, request: SynthesiaSignRequest) -> SynthesiaSignResponse:
        try:
            logger.debug(f"Making Synthesia API request: {request.message}")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._config.base_url}{self._config.sign_endpoint}",
                    params={"message": request.message},
                    headers=self._headers,
                )
            logger.info(f"Synthesia API response data: {response.__dict__}")
            response.raise_for_status()
            signature = response.text
            return SynthesiaSignResponse(signature=signature)
        except asyncio.TimeoutError:
            logger.exception("Synthesia API request timed out")
            # todo: update monitoring metrics
            raise
        except httpx.HTTPStatusError as e:
            logger.exception("Synthesia API request failed")
            if e.response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                # todo: update monitoring metrics
                logger.warning("Synthesia API rate limit exceeded")
            raise
        except Exception:
            logger.exception("Synthesia API request failed")
            raise
