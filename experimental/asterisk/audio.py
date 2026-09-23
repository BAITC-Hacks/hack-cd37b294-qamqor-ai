"""Small PCM helpers and deterministic energy endpointing for a local prototype.

This is an energy threshold detector, not a learned speech/noise classifier.
Only silence-ended utterances are final. Length-limited speech is discarded and
suppressed until silence, so a chopped sentence cannot reach the action core.
"""

import io
import math
import struct
import wave
from collections import deque
from dataclasses import dataclass


SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH


def _validate_pcm(pcm: bytes) -> None:
    if not isinstance(pcm, bytes):
        raise TypeError("PCM must be bytes")
    if len(pcm) % SAMPLE_WIDTH:
        raise ValueError("PCM has an incomplete 16-bit sample")


def pcm_rms(pcm: bytes) -> float:
    _validate_pcm(pcm)
    if not pcm:
        return 0.0
    return math.sqrt(sum(sample * sample for (sample,) in struct.iter_unpack("<h", pcm)) / (len(pcm) // 2))


def pcm8_to_wav(pcm: bytes, *, max_seconds: float = 30.0) -> bytes:
    """Wrap existing little-endian samples; no resampling or value changes."""
    _validate_pcm(pcm)
    if not math.isfinite(max_seconds) or not 0 < max_seconds <= 120:
        raise ValueError("max_seconds must be positive and at most 120")
    if not pcm or len(pcm) > max_seconds * BYTES_PER_SECOND:
        raise ValueError("PCM utterance is empty or exceeds duration limit")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


@dataclass(frozen=True, slots=True)
class VadEvent:
    kind: str  # speech_start | utterance | discarded
    pcm: bytes = b""
    reason: str = ""


class EnergyUtteranceDetector:
    """Endpoint 8 kHz S16LE PCM, independent of AudioSocket packet boundaries.

    ``feed`` emits speech_start after sustained threshold crossing, suitable for
    cancelling outbound audio; it emits utterance only after trailing silence.
    ``reset`` drops unfinished speech (including on hangup), never finalizes it.
    Pending audio is bounded by max_utterance_ms plus one <=65534-byte input.
    """

    def __init__(self, *, threshold: float = 500, frame_ms: int = 20,
                 start_ms: int = 40, silence_ms: int = 700, min_speech_ms: int = 160,
                 max_utterance_ms: int = 15000, pre_roll_ms: int = 200):
        if not math.isfinite(threshold) or not 0 < threshold <= 32768:
            raise ValueError("threshold must be a positive int16-scale RMS value")
        if frame_ms not in (10, 20, 30):
            raise ValueError("frame_ms must be 10, 20 or 30")
        values = (start_ms, silence_ms, min_speech_ms, max_utterance_ms, pre_roll_ms)
        if any(not isinstance(value, int) or value < 0 or value % frame_ms for value in values):
            raise ValueError("durations must be nonnegative multiples of frame_ms")
        if not 0 < start_ms <= min_speech_ms < max_utterance_ms <= 60000:
            raise ValueError("invalid start/minimum/maximum speech durations")
        if not 0 < silence_ms < max_utterance_ms or pre_roll_ms + start_ms >= max_utterance_ms:
            raise ValueError("invalid silence or pre-roll duration")
        self.threshold = threshold
        self.frame_ms = frame_ms
        self.frame_bytes = BYTES_PER_SECOND * frame_ms // 1000
        self.start_frames = start_ms // frame_ms
        self.silence_frames = silence_ms // frame_ms
        self.min_speech_ms = min_speech_ms
        self.max_frames = max_utterance_ms // frame_ms
        self.pre_frames = pre_roll_ms // frame_ms + self.start_frames
        self.reset()

    def reset(self) -> None:
        self.active = False
        self._pending = bytearray()
        self._pre = deque(maxlen=self.pre_frames)
        self._audio: list[bytes] = []
        self._onset = 0
        self._quiet = 0
        self._voiced_ms = 0
        self._suppressed = False

    def _clear_turn(self) -> None:
        self.active = False
        self._pre.clear()
        self._audio.clear()
        self._onset = self._quiet = self._voiced_ms = 0

    def feed(self, pcm: bytes) -> list[VadEvent]:
        _validate_pcm(pcm)
        if len(pcm) > 65534:
            raise ValueError("PCM feed exceeds packet limit")
        self._pending.extend(pcm)
        events = []
        while len(self._pending) >= self.frame_bytes:
            frame = bytes(self._pending[:self.frame_bytes])
            del self._pending[:self.frame_bytes]
            voiced = pcm_rms(frame) >= self.threshold
            if self._suppressed:
                self._quiet = 0 if voiced else self._quiet + 1
                if self._quiet >= self.silence_frames:
                    self._suppressed = False
                    self._clear_turn()
                continue
            if not self.active:
                self._pre.append(frame)
                self._onset = self._onset + 1 if voiced else 0
                if self._onset < self.start_frames:
                    continue
                self.active = True
                self._audio = list(self._pre)
                self._voiced_ms = self._onset * self.frame_ms
                self._quiet = 0
                events.append(VadEvent("speech_start"))
            else:
                self._audio.append(frame)
                self._quiet = 0 if voiced else self._quiet + 1
                if voiced:
                    self._voiced_ms += self.frame_ms
            if self._quiet >= self.silence_frames:
                if self._voiced_ms >= self.min_speech_ms:
                    # Keep at most 200ms of endpoint silence, not the entire
                    # detection wait, while preserving pre-roll and all speech.
                    keep = min(self._quiet, 200 // self.frame_ms)
                    trim = self._quiet - keep
                    frames = self._audio[:-trim] if trim else self._audio
                    events.append(VadEvent("utterance", b"".join(frames), "silence"))
                else:
                    events.append(VadEvent("discarded", reason="too_short"))
                self._clear_turn()
            elif len(self._audio) >= self.max_frames:
                events.append(VadEvent("discarded", reason="max_duration"))
                self._clear_turn()
                self._suppressed = True
        return events
