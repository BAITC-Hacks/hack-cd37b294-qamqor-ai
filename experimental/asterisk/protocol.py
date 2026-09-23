"""Bounded AudioSocket transport; this experimental adapter accepts PCM 8 kHz.

Protocol: https://docs.asterisk.org/Configuration/Channel-Drivers/AudioSocket/
The header is big endian; the PCM payload is signed 16-bit *little endian*.
Other documented sample-rate types are deliberately rejected, not misdecoded.
"""

import asyncio
import math
import struct
from dataclasses import dataclass


HANGUP = 0x00
UUID = 0x01
DTMF = 0x03
PCM_8K = 0x10
ERROR = 0xFF
DEFAULT_MAX_PAYLOAD = 4096


class ProtocolError(ValueError):
    """Malformed, unsupported, or oversized AudioSocket input."""


@dataclass(frozen=True, slots=True)
class Frame:
    kind: int
    payload: bytes


def _limits(timeout: float | None, max_payload: int) -> None:
    if not isinstance(max_payload, int) or not 16 <= max_payload <= 65535:
        raise ValueError("max_payload must be between 16 and 65535 bytes")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout must be positive and finite")


def _validate_header(kind: int, length: int, max_payload: int) -> None:
    if length > max_payload:
        raise ProtocolError("AudioSocket payload exceeds configured limit")
    if kind not in {HANGUP, UUID, DTMF, PCM_8K, ERROR}:
        raise ProtocolError(f"Unsupported AudioSocket type 0x{kind:02x}")
    if kind == HANGUP and length:
        raise ProtocolError("Hangup must have an empty payload")
    if kind == UUID and length != 16:
        raise ProtocolError("UUID must contain 16 binary bytes")
    if kind == DTMF and length != 1:
        raise ProtocolError("DTMF must contain one ASCII digit")
    if kind == PCM_8K and (not length or length % 2):
        raise ProtocolError("PCM must contain complete 16-bit samples")


def _validate_payload(kind: int, payload: bytes) -> None:
    if kind == DTMF and payload not in tuple(bytes([value]) for value in b"0123456789*#ABCD"):
        raise ProtocolError("Unsupported DTMF digit")


def encode_frame(kind: int, payload: bytes = b"", *, max_payload: int = DEFAULT_MAX_PAYLOAD) -> bytes:
    _limits(None, max_payload)
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    _validate_header(kind, len(payload), max_payload)
    _validate_payload(kind, payload)
    return struct.pack("!BH", kind, len(payload)) + payload


async def read_frame(reader: asyncio.StreamReader, *, timeout: float = 10.0,
                     max_payload: int = DEFAULT_MAX_PAYLOAD) -> Frame | None:
    """Read one frame within a total deadline; clean socket EOF returns None.

    Cancellation propagates. A timeout or ProtocolError requires closing this
    connection: a partially consumed packet must never be retried as a header.
    Validate the length before attempting a payload read/allocation.
    """
    _limits(timeout, max_payload)
    async with asyncio.timeout(timeout):
        try:
            header = await reader.readexactly(3)
        except asyncio.IncompleteReadError as exc:
            if not exc.partial:
                return None
            raise ProtocolError("Truncated AudioSocket header") from exc
        kind, length = struct.unpack("!BH", header)
        _validate_header(kind, length, max_payload)
        try:
            payload = await reader.readexactly(length)
        except asyncio.IncompleteReadError as exc:
            raise ProtocolError("Truncated AudioSocket payload") from exc
        _validate_payload(kind, payload)
        return Frame(kind, payload)


async def write_frame(writer: asyncio.StreamWriter, kind: int, payload: bytes = b"", *,
                      timeout: float = 10.0, max_payload: int = DEFAULT_MAX_PAYLOAD) -> None:
    """Write one validated frame with bounded backpressure wait."""
    _limits(timeout, max_payload)
    packet = encode_frame(kind, payload, max_payload=max_payload)
    writer.write(packet)
    async with asyncio.timeout(timeout):
        await writer.drain()
