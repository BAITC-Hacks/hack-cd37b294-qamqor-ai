"""Real loopback AudioSocket transport; unchanged web endpoints are mocked."""
import asyncio
from contextlib import asynccontextmanager
import io
import json
import struct
from uuid import uuid4
import wave

import httpx
import pytest

from experimental.asterisk.client import AudioConverter, CallState, ExistingPipeline
from experimental.asterisk.config import TelephonyConfig
from experimental.asterisk.protocol import DTMF, HANGUP, PCM_8K, UUID, encode_frame, read_frame
from experimental.asterisk.run import AudioSocketBridge, run


VOICE_FRAME = struct.pack('<h', 2000) * 160
SILENCE_FRAME = bytes(320)


async def eventually(predicate, timeout=3):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


class FakeConverter:
    def __init__(self):
        self.calls = []
        self.frames = 8

    async def decode(self, mp3):
        self.calls.append(mp3)
        return struct.pack('<h', int(mp3.decode().split(':')[-1]) * 1000) * (160 * self.frames)


class WebFixture:
    """Rejects every URL outside the current session/chat/voice APIs."""
    def __init__(self):
        self.requests = []
        self.sessions = {}
        self.chat_calls = []
        self.speech_calls = []
        self.interruptions = []
        self.transcripts = []
        self.fail_chat_session = None
        self.hold_chat = False
        self.hold_speech = False
        self.chat_started = asyncio.Event()
        self.chat_release = asyncio.Event()
        self.chat_cancelled = asyncio.Event()
        self.speech_started = asyncio.Event()
        self.speech_release = asyncio.Event()
        self.speech_cancelled = asyncio.Event()

    async def handle(self, request):
        path = request.url.path
        body = None
        if request.headers.get('content-type', '').startswith('application/json'):
            body = json.loads(request.content)
        self.requests.append((path, body, request))
        if path == '/health':
            return httpx.Response(200, json={'status': 'ok'})
        if path == '/api/voice/status':
            return httpx.Response(200, json={'configured': True})
        if path == '/api/session':
            sid = f'session-{len(self.sessions) + 1}'
            self.sessions[sid] = {'version': 0, 'language': body['language']}
            return httpx.Response(200, json={'conversation_id': sid, 'state_version': 0,
                                            'response_language': body['language']})
        if path == '/api/voice/transcribe':
            assert request.headers['content-type'] == 'audio/wav'
            with wave.open(io.BytesIO(request.content)) as wav:
                assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (8000, 1, 2)
                assert wav.getnframes() > 0
            transcript = self.transcripts.pop(0) if self.transcripts else {'text': 'Подтверждаю', 'final': True}
            return httpx.Response(200, json={**transcript, 'latency_ms': 5})
        if path == '/api/chat':
            self.chat_calls.append(body)
            self.chat_started.set()
            if self.hold_chat and len(self.chat_calls) == 1:
                try:
                    await self.chat_release.wait()
                except asyncio.CancelledError:
                    self.chat_cancelled.set()
                    raise
            if body['conversation_id'] == self.fail_chat_session:
                return httpx.Response(503, json={'detail': 'Fixture unavailable'})
            state = self.sessions[body['conversation_id']]
            assert body['expected_state_version'] == state['version']
            state['version'] += 1
            state['language'] = 'ru'
            return httpx.Response(200, json={
                'conversation_id': body['conversation_id'], 'turn_id': body['turn_id'],
                'state_version': state['version'], 'language': state['language'], 'text': 'Fixture answer',
                'pending_action': {'operation_id': 'must-never-be-auto-confirmed'},
            })
        if path == '/api/voice/speech':
            self.speech_calls.append(body)
            self.speech_started.set()
            if self.hold_speech and len(self.speech_calls) == 1:
                try:
                    await self.speech_release.wait()
                except asyncio.CancelledError:
                    self.speech_cancelled.set()
                    raise
            version = self.sessions[body['conversation_id']]['version']
            return httpx.Response(200, content=f'fixture-mp3:{version}'.encode())
        if path == '/api/voice/interruption':
            self.interruptions.append(body)
            return httpx.Response(200, json={'playback_stale': True})
        raise AssertionError('Unexpected external endpoint: ' + path)


class Peer:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.frames = []
        self.ended = asyncio.Event()
        self.task = asyncio.create_task(self.collect())

    async def collect(self):
        try:
            while frame := await read_frame(self.reader, timeout=5):
                self.frames.append((asyncio.get_running_loop().time(), frame))
        except (ConnectionError, OSError):
            pass
        finally:
            self.ended.set()

    async def send(self, kind, payload=b''):
        self.writer.write(encode_frame(kind, payload))
        await self.writer.drain()

    async def frames_in(self, pcm, count):
        for _ in range(count):
            self.writer.write(encode_frame(PCM_8K, pcm))
        await self.writer.drain()

    async def final_utterance(self):
        await self.frames_in(VOICE_FRAME, 10)
        await self.frames_in(SILENCE_FRAME, 35)

    async def close(self):
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, OSError):
            pass
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


@asynccontextmanager
async def loopback(fixture=None, converter=None, **config_values):
    fixture = fixture or WebFixture()
    converter = converter or FakeConverter()
    peers = []
    config = TelephonyConfig(enabled=True, io_timeout=1, idle_timeout=4, call_timeout=8, **config_values)
    async with httpx.AsyncClient(base_url='http://mock-web', transport=httpx.MockTransport(fixture.handle)) as client:
        pipeline = ExistingPipeline(client, converter)
        bridge = AudioSocketBridge(pipeline, config)
        server = await asyncio.start_server(bridge.handle, '127.0.0.1', 0, limit=8192)
        port = server.sockets[0].getsockname()[1]

        async def connect(send_uuid=True):
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            peer = Peer(reader, writer)
            peers.append(peer)
            if send_uuid:
                await peer.send(UUID, uuid4().bytes)
            return peer

        try:
            yield fixture, converter, bridge, connect
        finally:
            for peer in peers:
                await peer.close()
            server.close()
            await server.wait_closed()
            await bridge.close()


def test_silence_finalization_ordered_state_language_and_no_automatic_confirmation():
    async def check():
        async with loopback() as (web, converter, bridge, connect):
            peer = await connect()
            await eventually(lambda: len(web.sessions) == 1)
            await peer.frames_in(VOICE_FRAME, 10)
            await peer.send(DTMF, b'1')
            await peer.send(DTMF, b'#')
            await asyncio.sleep(0.06)
            assert web.chat_calls == []
            await peer.frames_in(SILENCE_FRAME, 35)
            await eventually(lambda: len(web.speech_calls) == 1)
            assert web.chat_calls[0]['expected_state_version'] == 0
            assert web.chat_calls[0]['language'] == 'kk'
            await peer.final_utterance()
            await eventually(lambda: len(web.speech_calls) == 2)
            assert [call['expected_state_version'] for call in web.chat_calls] == [0, 1]
            assert [call['language'] for call in web.chat_calls] == ['kk', 'ru']
            assert len({call['turn_id'] for call in web.chat_calls}) == 2
            assert all(call['input_mode'] == 'voice' and 'confirm_operation_id' not in call for call in web.chat_calls)
            stt_requests = [request for path, _, request in web.requests if path == '/api/voice/transcribe']
            assert [request.url.params['language'] for request in stt_requests] == ['kk', 'ru']
            assert web.sessions['session-1']['version'] == 2
    asyncio.run(check())


def test_output_is_fixed_320_byte_pcm_and_paced_over_loopback():
    async def check():
        async with loopback() as (web, converter, bridge, connect):
            peer = await connect()
            await peer.final_utterance()
            await eventually(lambda: sum(any(frame.payload) for _, frame in peer.frames) >= 6)
            audio = [(stamp, frame) for stamp, frame in peer.frames if any(frame.payload)][:6]
            assert all(frame.kind == PCM_8K and len(frame.payload) == 320 for _, frame in peer.frames)
            assert audio[-1][0] - audio[0][0] >= 0.07  # Six 20ms packets cannot be one burst.
            assert all(frame.payload == struct.pack('<h', 1000) * 160 for _, frame in audio)
    asyncio.run(check())


@pytest.mark.parametrize('ending', ['hangup', 'tcp-disconnect'])
def test_hangup_discards_unfinished_speech_without_calling_agent(ending):
    async def check():
        async with loopback() as (web, converter, bridge, connect):
            peer = await connect()
            await eventually(lambda: len(web.sessions) == 1)
            await peer.frames_in(VOICE_FRAME, 10)
            if ending == 'hangup':
                await peer.send(HANGUP)
            else:
                peer.writer.close()
                await peer.writer.wait_closed()
            await asyncio.wait_for(peer.ended.wait(), 2)
            await eventually(lambda: not bridge.active)
            assert web.chat_calls == [] and web.speech_calls == []
            assert not any(path == '/api/voice/transcribe' for path, _, _ in web.requests)
    asyncio.run(check())


def test_web_failure_closes_only_current_call_without_retry():
    async def check():
        async with loopback() as (web, converter, bridge, connect):
            web.fail_chat_session = 'session-1'
            first = await connect()
            await first.final_utterance()
            await asyncio.wait_for(first.ended.wait(), 2)
            await eventually(lambda: not bridge.active)
            assert len(web.chat_calls) == 1 and web.speech_calls == []
            second = await connect()
            await second.final_utterance()
            await eventually(lambda: len(web.speech_calls) == 1)
            assert len(web.chat_calls) == 2 and web.sessions['session-2']['version'] == 1
    asyncio.run(check())


@pytest.mark.parametrize('packet', [b'\x01\x00\x0f' + bytes(15), encode_frame(PCM_8K, VOICE_FRAME)], ids=['malformed-uuid', 'pcm-before-uuid'])
def test_bad_or_missing_uuid_closes_before_session_creation(packet):
    async def check():
        async with loopback() as (web, converter, bridge, connect):
            peer = await connect(False)
            peer.writer.write(packet)
            await peer.writer.drain()
            await asyncio.wait_for(peer.ended.wait(), 2)
            await eventually(lambda: not bridge.active)
            assert web.requests == []
            healthy = await connect()
            await eventually(lambda: len(web.sessions) == 1)
            assert not healthy.ended.is_set()
    asyncio.run(check())


def test_call_limit_rejects_excess_without_affecting_active_call():
    async def check():
        async with loopback(max_calls=1) as (web, converter, bridge, connect):
            first = await connect()
            await eventually(lambda: len(web.sessions) == 1)
            second = await connect(False)
            await asyncio.wait_for(second.ended.wait(), 2)
            assert len(web.sessions) == 1 and not first.ended.is_set()
            await first.final_utterance()
            await eventually(lambda: len(web.speech_calls) == 1)
    asyncio.run(check())


def test_barge_in_cancels_pending_tts_without_changing_committed_turn():
    async def check():
        fixture = WebFixture()
        fixture.hold_speech = True
        async with loopback(fixture) as (web, converter, bridge, connect):
            peer = await connect()
            await peer.final_utterance()
            await asyncio.wait_for(web.speech_started.wait(), 2)
            assert web.sessions['session-1']['version'] == 1
            await peer.frames_in(VOICE_FRAME, 10)
            await asyncio.wait_for(web.speech_cancelled.wait(), 2)
            await eventually(lambda: len(web.interruptions) == 1)
            assert web.sessions['session-1']['version'] == 1 and len(web.chat_calls) == 1
            web.speech_release.set()
            await peer.frames_in(SILENCE_FRAME, 35)
            await eventually(lambda: any(any(frame.payload) for _, frame in peer.frames))
            assert len(web.chat_calls) == 2 and web.chat_calls[1]['expected_state_version'] == 1
            assert converter.calls == [b'fixture-mp3:2']
            assert all(frame.payload == struct.pack('<h', 2000) * 160 for _, frame in peer.frames if any(frame.payload))
    asyncio.run(check())


def test_barge_in_stops_already_playing_audio_and_accepts_next_final_turn():
    async def check():
        converter = FakeConverter()
        converter.frames = 100
        async with loopback(converter=converter) as (web, decoder, bridge, connect):
            peer = await connect()
            await peer.final_utterance()
            await eventually(lambda: sum(any(frame.payload) for _, frame in peer.frames) >= 2)
            await peer.frames_in(VOICE_FRAME, 10)
            await eventually(lambda: len(web.interruptions) == 1)
            checkpoint = len(peer.frames)
            await eventually(lambda: len(peer.frames) >= checkpoint + 4)
            assert all(not any(frame.payload) for _, frame in peer.frames[-3:])
            assert len(web.chat_calls) == 1
            await peer.frames_in(SILENCE_FRAME, 35)
            await eventually(lambda: len(web.chat_calls) == 2)
            assert web.chat_calls[1]['expected_state_version'] == 1
    asyncio.run(check())


def test_new_utterance_does_not_cancel_chat_and_old_audio_is_never_requested():
    async def check():
        fixture = WebFixture()
        fixture.hold_chat = True
        async with loopback(fixture) as (web, converter, bridge, connect):
            peer = await connect()
            await peer.final_utterance()
            await asyncio.wait_for(web.chat_started.wait(), 2)
            await peer.final_utterance()
            await asyncio.sleep(0.04)
            assert not web.chat_cancelled.is_set() and len(web.chat_calls) == 1
            web.chat_release.set()
            await eventually(lambda: len(web.speech_calls) == 1)
            assert len(web.chat_calls) == 2
            assert [call['expected_state_version'] for call in web.chat_calls] == [0, 1]
            assert web.speech_calls[0]['turn_id'] == web.chat_calls[1]['turn_id']
            assert web.sessions['session-1']['version'] == 2
    asyncio.run(check())


@pytest.mark.parametrize('transcript', [{'final': False, 'text': 'unfinished'}, {'final': True, 'text': '  '}])
def test_pipeline_refuses_partial_or_empty_transcript(transcript):
    async def check():
        web = WebFixture()
        web.transcripts = [transcript]
        async with httpx.AsyncClient(base_url='http://mock-web', transport=httpx.MockTransport(web.handle)) as client:
            pipeline = ExistingPipeline(client, FakeConverter())
            state = await pipeline.create('kk')
            with pytest.raises(ValueError):
                await pipeline.turn(state, VOICE_FRAME * 10)
            assert state.version == 0 and web.chat_calls == []
    asyncio.run(check())


@pytest.mark.parametrize('pcm', [b'', b'\x00', bytes(8000 * 2 * 30 + 2)], ids=['empty', 'partial-sample', 'oversized'])
def test_input_pcm_limits_fail_before_http_request(pcm):
    async def check():
        web = WebFixture()
        async with httpx.AsyncClient(base_url='http://mock-web', transport=httpx.MockTransport(web.handle)) as client:
            pipeline = ExistingPipeline(client, FakeConverter())
            with pytest.raises(ValueError):
                await pipeline.turn(CallState('unused', 0, 'kk'), pcm)
            assert web.requests == []
    asyncio.run(check())


def test_missing_converter_stops_before_network_or_listener(monkeypatch):
    monkeypatch.setattr('experimental.asterisk.client.shutil.which', lambda _: None)
    async def must_not_listen(*args, **kwargs):
        pytest.fail('Missing optional decoder must fail before binding a listener')
    monkeypatch.setattr('experimental.asterisk.run.asyncio.start_server', must_not_listen)
    def must_not_make_http(*args, **kwargs):
        pytest.fail('Missing optional decoder must fail before creating HTTP transport')
    monkeypatch.setattr('experimental.asterisk.run.httpx.AsyncClient', must_not_make_http)
    with pytest.raises(RuntimeError, match='decoder unavailable'):
        asyncio.run(run(TelephonyConfig(enabled=True)))


@pytest.mark.parametrize(('health', 'configured'), [('degraded', True), ('ok', False)])
def test_preflight_refuses_unhealthy_existing_voice_pipeline(health, configured):
    async def check():
        paths = []
        def handle(request):
            paths.append(request.url.path)
            return httpx.Response(200, json={'status': health} if request.url.path == '/health' else {'configured': configured})
        async with httpx.AsyncClient(base_url='http://mock-web', transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(RuntimeError, match='pipeline unavailable'):
                await ExistingPipeline(client, FakeConverter()).preflight()
            assert paths == ['/health', '/api/voice/status']
    asyncio.run(check())
