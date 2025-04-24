from pydantic import BaseModel


class CryptoSignResponse(BaseModel):
    request_id: str
    status: int
    signature: str | None = None
