from typing import Protocol


class STTProvider(Protocol):
    async def transcribe(self, audio: bytes, mime: str, language: str | None = None) -> str: ...


class TTSProvider(Protocol):
    async def synthesize(self, text: str, language: str) -> bytes: ...
