from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import dotenv_values
from app.catalog.loader import PROJECT_ROOT, DEFAULT_DATASET


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-6-astra"
    timeout_seconds: float = 90
    eval_concurrency: int = 2
    dataset_path: Path = DEFAULT_DATASET

    @classmethod
    def load(cls, env_file: Path | None = None):
        values = {**dotenv_values(env_file or PROJECT_ROOT / ".env"), **os.environ}
        settings = cls(
            api_key=(values.get("OPENAI_API_KEY") or "").strip(),
            base_url=(values.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
            model=values.get("CALLAI_MODEL") or "gpt-6-astra",
            timeout_seconds=float(values.get("CALLAI_TIMEOUT_SECONDS") or 90),
            eval_concurrency=int(values.get("CALLAI_EVAL_CONCURRENCY") or 2),
            dataset_path=Path(values.get("CALLAI_DATASET_PATH") or DEFAULT_DATASET),
        )
        if settings.timeout_seconds <= 0 or settings.eval_concurrency < 1:
            raise ConfigurationError("Timeout and concurrency must be positive")
        return settings

    def require_api_key(self):
        if not self.api_key or self.api_key.lower() in {"your-key", "replace-me", "sk-..."}:
            raise ConfigurationError("OPENAI_API_KEY is missing. Set it locally in halyk-callai/.env; never paste it into logs.")
