"""Standard-library-only configuration, independent of the main app settings."""
from dataclasses import dataclass
import math
import os
from collections.abc import Mapping
from urllib.parse import urlsplit


def is_enabled(values: Mapping[str, str] | None = None) -> bool:
    values = os.environ if values is None else values
    return values.get('TELEPHONY_ENABLED', 'false').strip().lower() == 'true'


@dataclass(frozen=True)
class TelephonyConfig:
    enabled: bool = False
    host: str = '127.0.0.1'
    port: int = 9092
    backend_url: str = 'http://127.0.0.1:8000'
    language: str = 'kk'
    ffmpeg: str = 'ffmpeg'
    api_timeout: float = 120.0
    io_timeout: float = 5.0
    idle_timeout: float = 60.0
    call_timeout: float = 600.0
    max_calls: int = 1
    vad_threshold: float = 500.0

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None):
        values = os.environ if values is None else values
        # Disabled means even malformed experimental settings are irrelevant.
        if not is_enabled(values):
            return cls()
        config = cls(
            enabled=True,
            host=values.get('TELEPHONY_HOST', '127.0.0.1'),
            port=int(values.get('TELEPHONY_PORT', '9092')),
            backend_url=values.get('TELEPHONY_BACKEND_URL', 'http://127.0.0.1:8000').rstrip('/'),
            language=values.get('TELEPHONY_LANGUAGE', 'kk'),
            ffmpeg=values.get('TELEPHONY_FFMPEG', 'ffmpeg'),
            api_timeout=float(values.get('TELEPHONY_API_TIMEOUT_SECONDS', '120')),
            max_calls=int(values.get('TELEPHONY_MAX_CALLS', '1')),
            vad_threshold=float(values.get('TELEPHONY_VAD_THRESHOLD', '500')),
        )
        url = urlsplit(config.backend_url)
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('TELEPHONY_BACKEND_URL must be an HTTP base URL without credentials/query/fragment')
        if not config.host or not 1 <= config.port <= 65535 or config.language not in {'ru', 'kk'}:
            raise ValueError('Invalid telephony bind address, port or language')
        if not 1 <= config.max_calls <= 4:
            raise ValueError('TELEPHONY_MAX_CALLS must be 1..4 for this experiment')
        if not math.isfinite(config.api_timeout) or not 1 <= config.api_timeout <= 240:
            raise ValueError('TELEPHONY_API_TIMEOUT_SECONDS must be 1..240')
        if not math.isfinite(config.vad_threshold) or not 1 <= config.vad_threshold <= 32767:
            raise ValueError('Invalid TELEPHONY_VAD_THRESHOLD')
        return config
