import math
import os
from typing import Dict, TypedDict


class LangConfig(TypedDict):
    voice: str
    name: str


LANG_SETTINGS: Dict[str, LangConfig] = {
    "ja": {"voice": "ja-JP-NanamiNeural", "name": "Japanese"},
    "en": {"voice": "en-US-AndrewNeural", "name": "English"},
    "ko": {"voice": "ko-KR-SunHiNeural", "name": "Korean"},
}


def get_discord_token() -> str:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable is not set.")
    return token


def get_gemini_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
    return key


def get_shutdown_timeout() -> float:
    raw_timeout = os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "20")
    try:
        timeout = float(raw_timeout)
    except ValueError as error:
        raise ValueError(
            "SHUTDOWN_TIMEOUT_SECONDS must be a positive number."
        ) from error

    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("SHUTDOWN_TIMEOUT_SECONDS must be a positive number.")
    return timeout
