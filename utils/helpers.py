from typing import TypeVar
import logging
import os

from pydantic import BaseModel

from utils.auth import UserId


logger = logging.getLogger(__name__)

T = TypeVar("T")


class RequestHeaders(BaseModel):
    user_id: UserId
    request_id: str


def is_docker() -> bool:
    return os.path.exists("/.dockerenv")
