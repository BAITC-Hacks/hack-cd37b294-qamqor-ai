import asyncio
import io
import struct
import uuid
import wave

import pytest

from experimental.asterisk.protocol import (
    DTMF, ERROR, HANGUP, PCM_8K, UUID, Frame, ProtocolError,
    encode_frame, read_frame, write_frame,
)
from experimental.asterisk.audio import EnergyUtteranceDetector, pcm8_to_wav, pcm_rms


def run_read(data, **kwargs):
    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        return await read_frame(reader, **kwargs)
    return asyncio.run(run())


def tone(ms, amplitude=1000):
    return struct.pack("<h", amplitude) * (8 * ms)


def test_official_wire_formats_and_sample_byte_order():
    value = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
    assert encode_frame(UUID, value.bytes) == b"\x01\x00\x10" + value.bytes
    assert encode_frame(HANGUP) == b"\x00\x00\x00"
    assert encode_frame(DTMF, b"#") == b"\x03\x00\x01#"
    samples = struct.pack("<hhh", 1, -1, -32768)
    assert run_read(encode_frame(PCM_8K, samples)) == Frame(PCM_8K, samples)
    assert run_read(encode_frame(ERROR)) == Frame(ERROR, b"")


def test_two_coalesced_frames_and_split_packet_read():
    async def run():
        reader = asyncio.StreamReader()
        data = encode_frame(DTMF, b"1") + encode_frame(HANGUP)
        async def feed():
            for chunk in (data[:1], data[1:3], data[3:]):
                reader.feed_data(chunk)
                await asyncio.sleep(0)
            reader.feed_eof()
        task = asyncio.create_task(feed())
        assert await read_frame(reader) == Frame(DTMF, b"1")
        assert await read_frame(reader) == Frame(HANGUP, b"")
        assert await read_frame(reader) is None
        await task
    asyncio.run(run())


@pytest.mark.parametrize("data", [b"\x01", b"\x01\x00\x10abc", b"\x10\x00\x03abc", b"\x12\x00\x02aa", b"\x00\x00\x01x", b"\x03\x00\x01z", b"\x01\x00\x01x", b"\x10\x00\x00"])
def test_malformed_or_unsupported_frames_rejected(data):
    with pytest.raises(ProtocolError):
        run_read(data)


def test_oversized_header_rejected_before_waiting_for_payload():
    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(b"\x10\xff\xfe")
        with pytest.raises(ProtocolError, match="limit"):
            await read_frame(reader, timeout=.05)
    asyncio.run(run())


def test_header_and_payload_deadlines():
    async def run(data):
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        with pytest.raises(TimeoutError):
            await read_frame(reader, timeout=.01)
    asyncio.run(run(b""))
    asyncio.run(run(b"\x01\x00\x10"))


def test_writer_drains_and_respects_timeout():
    class Writer:
        data = b""
        async def drain(self):
            await asyncio.sleep(0)
        def write(self, data):
            self.data += data
    writer = Writer()
    asyncio.run(write_frame(writer, DTMF, b"A"))
    assert writer.data == b"\x03\x00\x01A"
    class BlockedWriter(Writer):
        async def drain(self):
            await asyncio.Event().wait()
    with pytest.raises(TimeoutError):
        asyncio.run(write_frame(BlockedWriter(), HANGUP, timeout=.01))


def test_wav_contains_identical_8000hz_mono_samples():
    pcm = struct.pack("<hhhh", -32768, -1, 0, 32767)
    with wave.open(io.BytesIO(pcm8_to_wav(pcm)), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (8000, 1, 2)
        assert wav.readframes(100) == pcm
    assert pcm_rms(tone(20, -1000)) == 1000
    assert pcm_rms(b"") == 0


@pytest.mark.parametrize("pcm", [b"", b"a", tone(1000)], ids=["empty", "partial_sample", "oversized"])
def test_wav_rejects_empty_partial_or_oversized_audio(pcm):
    with pytest.raises(ValueError):
        pcm8_to_wav(pcm, max_seconds=.5)


def test_silence_only_never_becomes_an_utterance():
    detector = EnergyUtteranceDetector()
    for _ in range(100):
        assert detector.feed(tone(20, 0)) == []
    assert not detector.active


def test_endpoint_preserves_preroll_all_speech_and_short_trailing_silence():
    detector = EnergyUtteranceDetector()
    assert detector.feed(tone(300, 0)) == []
    events = detector.feed(tone(200))
    assert [event.kind for event in events] == ["speech_start"]
    assert detector.active
    assert detector.feed(tone(680, 0)) == []
    final = detector.feed(tone(20, 0))
    assert [(event.kind, event.reason) for event in final] == [("utterance", "silence")]
    assert final[0].pcm == tone(200, 0) + tone(200) + tone(200, 0)
    assert not detector.active


def test_pcm_packet_boundaries_do_not_change_endpoint_result():
    source = tone(200, 0) + tone(300) + tone(720, 0)
    a, b = EnergyUtteranceDetector(), EnergyUtteranceDetector()
    expected = a.feed(source)
    actual = []
    for index in range(0, len(source), 74):
        actual += b.feed(source[index:index+74])
    assert actual == expected


def test_short_noise_is_discarded_without_final_pcm():
    detector = EnergyUtteranceDetector()
    assert detector.feed(tone(20)) == []
    assert detector.feed(tone(700, 0)) == []
    events = detector.feed(tone(60) + tone(700, 0))
    assert [(e.kind, e.reason, bool(e.pcm)) for e in events] == [("speech_start", "", False), ("discarded", "too_short", False)]


def test_maximum_utterance_discards_and_suppresses_continuation_until_silence():
    detector = EnergyUtteranceDetector(max_utterance_ms=1000)
    events = detector.feed(tone(1200))
    assert [(e.kind, e.reason) for e in events] == [("speech_start", ""), ("discarded", "max_duration")]
    assert not any(event.pcm for event in events)
    assert detector.feed(tone(1000)) == []
    assert detector.feed(tone(700, 0)) == []
    events = detector.feed(tone(200) + tone(700, 0))
    assert [event.kind for event in events] == ["speech_start", "utterance"]


def test_reset_drops_incomplete_audio_instead_of_finalizing_it():
    detector = EnergyUtteranceDetector()
    assert detector.feed(tone(200))[0].kind == "speech_start"
    detector.reset()
    assert not detector.active
    assert detector.feed(tone(700, 0)) == []


@pytest.mark.parametrize("options", [{"threshold":0}, {"silence_ms":0}, {"frame_ms":7}, {"pre_roll_ms":1}, {"max_utterance_ms":100}])
def test_invalid_detector_configuration_is_rejected(options):
    with pytest.raises(ValueError):
        EnergyUtteranceDetector(**options)
