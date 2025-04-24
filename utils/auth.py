from typing import NewType

from fastapi import HTTPException
from pydantic import BaseModel

from configs.config import SynthesiaAPIConfig


UserId = NewType("UserId", str)


class AuthInfo(BaseModel):
    user_id: UserId


def get_auth_info(authorization: str, config: SynthesiaAPIConfig) -> AuthInfo:
    # this is dummy verification just for task, user_id is hardcoded
    if authorization != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return AuthInfo(user_id="1")
