"""HTTP client for the unchanged web voice APIs; no separate agent/provider."""
import asyncio
from dataclasses import dataclass
import shutil
from uuid import uuid4

import httpx
from .audio import pcm8_to_wav


class AudioConverter:
    """Optional external decoder, required only by the enabled sidecar."""
    def __init__(self, executable='ffmpeg'):
        self.executable = shutil.which(executable)
        if not self.executable:
            raise RuntimeError('Experimental audio decoder unavailable')

    async def decode(self, mp3: bytes) -> bytes:
        if not mp3 or len(mp3) > 10 * 1024 * 1024:
            raise ValueError('TTS audio size outside experiment limits')
        process = await asyncio.create_subprocess_exec(
            self.executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'mp3', '-i', 'pipe:0', '-f', 's16le', '-acodec', 'pcm_s16le',
            '-ar', '8000', '-ac', '1', 'pipe:1',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            pcm, _ = await asyncio.wait_for(process.communicate(mp3), timeout=15)
            if process.returncode or not pcm or len(pcm) % 2 or len(pcm) > 8000 * 2 * 180:
                raise ValueError('TTS decode failed or reply exceeds experiment limit')
            return pcm
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


@dataclass
class CallState:
    conversation_id: str
    version: int
    language: str


class ExistingPipeline:
    def __init__(self, client: httpx.AsyncClient, converter):
        self.client, self.converter = client, converter

    async def preflight(self):
        health = await self.client.get('/health', timeout=5)
        health.raise_for_status()
        status = await self.client.get('/api/voice/status', timeout=5)
        status.raise_for_status()
        if health.json().get('status') != 'ok' or not status.json().get('configured'):
            raise RuntimeError('Web voice pipeline unavailable')

    async def create(self, language):
        response = await self.client.post('/api/session', json={'language': language})
        response.raise_for_status()
        state = response.json()
        return CallState(state['conversation_id'], state['state_version'], state['response_language'])

    async def turn(self, state: CallState, pcm: bytes):
        response = await self.client.post('/api/voice/transcribe', params={'language': state.language},
            content=pcm8_to_wav(pcm), headers={'Content-Type': 'audio/wav'})
        response.raise_for_status()
        transcript = response.json()
        if transcript.get('final') is not True or not transcript.get('text', '').strip():
            raise ValueError('Only final recognized utterances may enter the shared agent')
        # Never infer a confirmation token from speech/DTMF. This experimental
        # transport leaves action confirmations to the existing Web UI.
        response = await self.client.post('/api/chat', json={
            'conversation_id': state.conversation_id, 'turn_id': str(uuid4()),
            'text': transcript['text'], 'language': state.language,
            'expected_state_version': state.version, 'input_mode': 'voice',
            'stt_latency_ms': transcript.get('latency_ms'),
        })
        # No automatic retry after an ambiguous network failure or timeout.
        response.raise_for_status()
        answer = response.json()
        state.version, state.language = answer['state_version'], answer['language']
        return answer

    async def speech(self, answer):
        response = await self.client.post('/api/voice/speech', json={
            'conversation_id': answer['conversation_id'], 'turn_id': answer['turn_id'],
        })
        response.raise_for_status()
        return await self.converter.decode(response.content)

    async def interrupt(self, conversation_id, turn_id):
        try:
            await self.client.post('/api/voice/interruption', timeout=3,
                json={'conversation_id': conversation_id, 'turn_id': turn_id})
        except httpx.HTTPError:
            pass  # Diagnostic event only; never changes committed state.
