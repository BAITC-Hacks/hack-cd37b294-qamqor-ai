"""Speech output checks only: no live providers, chat or routing requests."""
import asyncio
from copy import deepcopy
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request

from app.config.settings import Settings
from app.main import create_app
from app.voice.config import SpeechConfig
from app.voice.providers import OpenAIAudio
from app.voice.routes import VoiceTurn, voice_routes


@pytest.fixture(autouse=True)
def isolated_speech_environment(monkeypatch):
    for name in (
        'TTS_PROVIDER', 'TTS_MODEL', 'TTS_VOICE_RU', 'TTS_VOICE_KK',
        'TTS_SPEED', 'TTS_INSTRUCTIONS', 'CALLAI_TTS_MODEL', 'CALLAI_TTS_VOICE',
        'CALLAI_VOICE_API_KEY', 'CALLAI_VOICE_BASE_URL', 'CALLAI_STT_MODEL',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('CALLAI_VOICE_ENABLED', 'true')
    monkeypatch.setattr('app.voice.providers.dotenv_values', lambda _: {})


class AudioChunks(httpx.AsyncByteStream):
    def __init__(self, chunks=(b'ID3-first', b'-second'), before_chunk=None, failure=None):
        self.chunks = chunks
        self.before_chunk = before_chunk
        self.failure = failure
        self.closed = False

    async def __aiter__(self):
        for index, chunk in enumerate(self.chunks):
            if self.before_chunk:
                self.before_chunk(index)
            yield chunk
        if self.failure:
            raise self.failure

    async def aclose(self):
        self.closed = True


def make_app(tmp_path, stream, seen=None, status=200):
    def handler(request):
        assert request.url.path.endswith('/audio/speech'), 'Unexpected non-TTS model call'
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, stream=stream, headers={'Content-Type': 'audio/mpeg'})
    return create_app(Settings(api_key='test-only'), httpx.MockTransport(handler),
                      database_path=tmp_path / 'speech.sqlite')


def committed_turn(app, language='ru'):
    service = app.state.conversations
    service.router.route = AsyncMock(side_effect=AssertionError('Speech must not route'))
    state = service.create('ru')
    state['state_version'] = 4
    state['pending_action'] = {'operation_id': 'unchanged-operation', 'action': 'update_contact'}
    answer = {'text': '**Сәлеметсіз бе.**' if language == 'kk' else '**Здравствуйте.**',
              'language': language, 'state_version': 4,
              'latency': {'total_text_ms': 100, 'stt_ms': 10}}
    service.repository.save(state, ('speech-turn', 'committed-request', json.dumps(answer)))
    body = {'conversation_id': state['conversation_id'], 'turn_id': 'speech-turn'}
    return state, answer, body


def business_snapshot(app, body):
    repository = app.state.repository
    with repository.connect() as db:
        backend = db.execute('SELECT body FROM backend').fetchone()['body']
        operations = [tuple(row) for row in db.execute('SELECT * FROM operations')]
    return (repository.get(body['conversation_id']),
            repository.previous_turn(body['conversation_id'], body['turn_id']), backend, operations)


def tts_events(app):
    return [event for event in app.state.tracer.recent.values() if event['type'] == 'tts']


def test_new_environment_names_override_legacy_and_environment_overrides_dotenv(monkeypatch):
    monkeypatch.setattr('app.voice.providers.dotenv_values', lambda _: {
        'TTS_VOICE_RU': 'nova', 'TTS_VOICE_KK': 'sage', 'TTS_SPEED': '0.9',
        'CALLAI_TTS_MODEL': 'tts-1', 'CALLAI_TTS_VOICE': 'alloy',
    })
    monkeypatch.setenv('TTS_MODEL', 'gpt-4o-mini-tts')
    monkeypatch.setenv('TTS_VOICE_RU', 'marin')
    monkeypatch.setenv('TTS_SPEED', '1.05')
    provider = OpenAIAudio(Settings(api_key='test-only'), None)
    assert provider.speech_config == SpeechConfig(model='gpt-4o-mini-tts', voice_ru='marin',
                                                voice_kk='sage', speed=1.05)
    assert SpeechConfig.from_values({'CALLAI_TTS_MODEL': 'tts-1-hd', 'CALLAI_TTS_VOICE': 'alloy'}) == SpeechConfig(
        model='tts-1-hd', voice_ru='alloy', voice_kk='alloy')
    assert SpeechConfig.from_values({}) == SpeechConfig()


@pytest.mark.parametrize('values', [
    {'TTS_PROVIDER': 'unsupported'}, {'TTS_SPEED': 'NaN'}, {'TTS_SPEED': 'inf'},
    {'TTS_SPEED': '0.249'}, {'TTS_SPEED': '4.01'}, {'TTS_SPEED': 'fast'},
])
def test_invalid_configuration_fails_explicitly(values):
    with pytest.raises(ValueError):
        SpeechConfig.from_values(values)


@pytest.mark.parametrize(('language', 'voice', 'language_cue'), [
    ('ru', 'marin', 'Russian stress'), ('kk', 'cedar', 'Kazakh vowel harmony'),
])
def test_payload_uses_explicit_final_language_and_normalizes_only_speech(monkeypatch, language, voice, language_cue):
    monkeypatch.setenv('TTS_VOICE_RU', 'marin')
    monkeypatch.setenv('TTS_VOICE_KK', 'cedar')
    monkeypatch.setenv('TTS_SPEED', '0.95')
    monkeypatch.setenv('TTS_INSTRUCTIONS', 'Do not rush names.')
    provider = OpenAIAudio(Settings(api_key='test-only'), None)
    original = '**Ақша списали, бірақ полис келмеді.**'
    payload = provider.speech_payload(original, language)
    assert payload['voice'] == voice and payload['speed'] == 0.95
    assert payload['input'] == 'Ақша списали, бірақ полис келмеді.'
    assert payload['response_format'] == 'mp3'
    assert language_cue in payload['instructions']
    assert 'call-center specialist' in payload['instructions']
    assert 'Do not rush names.' in payload['instructions']
    assert original == '**Ақша списали, бірақ полис келмеді.**'


@pytest.mark.parametrize('model', ['tts-1', 'tts-1-hd'])
def test_legacy_models_do_not_receive_unsupported_instructions(monkeypatch, model):
    monkeypatch.setenv('TTS_MODEL', model)
    payload = OpenAIAudio(Settings(api_key='test-only'), None).speech_payload('Здравствуйте.', 'ru')
    assert payload['model'] == model and 'instructions' not in payload


@pytest.mark.parametrize(('text', 'language'), [('', 'ru'), ('x' * 4097, 'ru'), ('Ответ.', 'mixed')])
def test_invalid_speech_rejected_before_provider_call(text, language):
    with pytest.raises(ValueError):
        OpenAIAudio(Settings(api_key='test-only'), None).speech_payload(text, language)


@pytest.mark.parametrize('streaming', [False, True])
def test_speech_endpoint_preserves_api_and_business_state(tmp_path, monkeypatch, streaming):
    monkeypatch.setenv('TTS_VOICE_RU', 'marin')
    monkeypatch.setenv('TTS_VOICE_KK', 'cedar')
    async def run():
        seen = []
        chunks = AudioChunks()
        app = make_app(tmp_path, chunks, seen)
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app, 'kk')
            before = business_snapshot(app, body)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                response = await client.post('/api/voice/speech', params={'stream': str(streaming).lower()}, json=body)
                assert response.status_code == 200 and response.content == b'ID3-first-second'
                assert response.headers['content-type'] == 'audio/mpeg'
                assert response.headers['cache-control'] == 'no-store'
                assert seen[0]['voice'] == 'cedar'  # Stored session started RU; committed response is KK.
                assert seen[0]['input'] == 'Сәлеметсіз бе.'
                assert chunks.closed
                assert business_snapshot(app, body) == before
                app.state.router.route.assert_not_called()
                event = tts_events(app)[0]
                assert event['bytes'] == len(response.content)
                if streaming:
                    assert response.headers['x-tts-streaming'] == 'true'
                    assert float(response.headers['x-tts-first-byte-ms']) >= 0
                    assert event['outcome'] == 'complete'
                    assert 0 <= event['latency']['tts_first_byte_ms'] <= event['latency']['tts_ms']
                else:
                    assert float(response.headers['x-tts-latency-ms']) >= 0
                    assert event['latency']['total_voice_processing_ms'] == 110 + event['latency']['tts_ms']
    asyncio.run(run())


def test_stream_rejects_state_changed_during_first_chunk_and_closes_upstream(tmp_path):
    async def run():
        chunks = AudioChunks()
        app = make_app(tmp_path, chunks)
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app)
            changed = deepcopy(state)
            changed['state_version'] += 1
            chunks.before_chunk = lambda index: app.state.repository.save(changed) if index == 0 else None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                response = await client.post('/api/voice/speech?stream=true', json=body)
            assert response.status_code == 409 and chunks.closed
            assert app.state.repository.get(body['conversation_id']) == changed
    asyncio.run(run())


def test_stream_stops_before_next_chunk_when_state_becomes_stale(tmp_path):
    async def run():
        chunks = AudioChunks()
        app = make_app(tmp_path, chunks)
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app)
            changed = deepcopy(state)
            changed['state_version'] += 1
            chunks.before_chunk = lambda index: app.state.repository.save(changed) if index == 1 else None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                response = await client.post('/api/voice/speech?stream=true', json=body)
            assert response.content == b'ID3-first' and chunks.closed
            assert tts_events(app)[0]['outcome'] == 'stale'
            assert tts_events(app)[0]['bytes'] == len(b'ID3-first')
            assert app.state.repository.get(body['conversation_id']) == changed
    asyncio.run(run())


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('kind', ['upstream-error', 'empty-audio'])
def test_provider_failure_retains_saved_answer_and_closes_stream(tmp_path, streaming, kind):
    async def run():
        chunks = AudioChunks(())
        app = make_app(tmp_path, chunks, status=503 if kind == 'upstream-error' else 200)
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app)
            before = business_snapshot(app, body)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                response = await client.post('/api/voice/speech', params={'stream': str(streaming).lower()}, json=body)
            assert response.status_code == 502 and chunks.closed
            assert business_snapshot(app, body) == before
            app.state.router.route.assert_not_called()
    asyncio.run(run())


def test_explicit_stream_cancellation_closes_provider_and_records_interruption(tmp_path):
    async def run():
        chunks = AudioChunks()
        app = make_app(tmp_path, chunks)
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app)
            before = business_snapshot(app, body)
            endpoint = next(route.endpoint for route in voice_routes().routes if route.path == '/api/voice/speech')
            response = await endpoint(VoiceTurn(**body), Request({'type': 'http', 'app': app}), stream=True)
            iterator = response.body_iterator
            assert await anext(iterator) == b'ID3-first'
            assert not chunks.closed
            await iterator.aclose()
            assert chunks.closed and tts_events(app)[0]['outcome'] == 'interrupted'
            assert business_snapshot(app, body) == before
    asyncio.run(run())


def test_upstream_midstream_failure_is_not_reported_as_complete(tmp_path):
    async def run():
        chunks = AudioChunks((b'ID3-first',), failure=httpx.ReadError('fixture failure'))
        app = make_app(tmp_path, chunks)
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app)
            before = business_snapshot(app, body)
            endpoint = next(route.endpoint for route in voice_routes().routes if route.path == '/api/voice/speech')
            response = await endpoint(VoiceTurn(**body), Request({'type': 'http', 'app': app}), stream=True)
            iterator = response.body_iterator
            assert await anext(iterator) == b'ID3-first'
            with pytest.raises(httpx.ReadError):
                await anext(iterator)
            assert chunks.closed and tts_events(app)[0]['outcome'] == 'failed'
            assert business_snapshot(app, body) == before
    asyncio.run(run())


def test_playback_metrics_accept_missing_measurements_without_fabricating_zero(tmp_path):
    async def run():
        app = make_app(tmp_path, AudioChunks())
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app)
            before = business_snapshot(app, body)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                response = await client.post('/api/voice/playback', json={**body, 'streaming': True,
                    'response_ready_to_first_byte_ms': 12.5, 'first_playback_ms': None, 'complete_stream_ms': None})
                assert response.status_code == 200 and response.json() == {'recorded': True}
                events = [event for event in app.state.tracer.recent.values() if event['type'] == 'tts_playback']
                assert events[0]['latency'] == {'response_ready_to_first_byte_ms': 12.5}
                assert 'client reported' in events[0]['measurement']
                assert business_snapshot(app, body) == before
                app.state.router.route.assert_not_called()
    asyncio.run(run())


@pytest.mark.parametrize('metrics', [
    {'first_playback_ms': -1}, {'complete_stream_ms': 600001},
    {'first_playback_ms': 'NaN'}, {'response_ready_to_first_byte_ms': 'inf'},
    {'first_playback_ms': 12, 'unknown_metric': 5},
])
def test_invalid_playback_metrics_are_rejected_without_mutation(tmp_path, metrics):
    async def run():
        app = make_app(tmp_path, AudioChunks())
        async with app.router.lifespan_context(app):
            state, answer, body = committed_turn(app)
            before = business_snapshot(app, body)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                response = await client.post('/api/voice/playback', json={**body, 'streaming': True, **metrics})
            assert response.status_code == 422
            assert business_snapshot(app, body) == before
            assert not app.state.tracer.recent
    asyncio.run(run())
