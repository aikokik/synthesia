# src/config.py
from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass
class InterfaceConfig:
    api_key: str | None


class SynthesiaAPIConfig(InterfaceConfig):
    def __init__(self) -> None:
        self.api_key = os.getenv("SYNTHESIA_API_KEY")
        if not self.api_key:
            raise ValueError("SYNTHESIA_API_KEY not found in environment variables")
        self.base_url = "https://hiring.api.synthesia.io"
        self.sign_endpoint = "/crypto/sign"
        self.verify_endpoint = "/crypto/verify"
        self.timeout = 108  # 1.8 minutes to be within the 2 minute limit
