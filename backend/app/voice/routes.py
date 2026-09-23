import json
import time
from uuid import uuid4
import httpx
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from app.state.models import now


class VoiceTurn(BaseModel):
    conversation_id: str
    turn_id: str


class PlaybackMetrics(VoiceTurn):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    response_ready_to_first_byte_ms: float | None = Field(default=None, ge=0, le=600000)
    first_playback_ms: float | None = Field(default=None, ge=0, le=600000)
    complete_stream_ms: float | None = Field(default=None, ge=0, le=600000)
    streaming: bool


def voice_routes():
    routes=APIRouter(prefix='/api/voice')

    def provider(request):
        value=request.app.state.audio
        if not value.configured: raise HTTPException(503,'Voice unavailable: configure audio credentials or use text.')
        return value

    @routes.get('/status')
    async def status(request: Request):
        p=request.app.state.audio
        return {'configured':p.configured,'api_access_verified':False,'stt_model':p.stt_model,'tts_model':p.tts_model,
                'transport':'final-utterance','ai_generated_voice':True,'tts':p.speech_config.public()}

    @routes.post('/transcribe')
    async def transcribe(request: Request, language: Literal['ru','kk'] | None = None):
        p=provider(request); tick=time.perf_counter()
        mime=request.headers.get('content-type','').split(';')[0]
        if mime not in {'audio/webm','audio/mp4','audio/wav','audio/mpeg','audio/ogg'}: raise HTTPException(415,'Unsupported audio format')
        chunks=bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks)>20*1024*1024: raise HTTPException(413,'Audio limit: 20 MB')
        if len(chunks)<32: raise HTTPException(422,'Empty recording')
        try: text=await p.transcribe(bytes(chunks),mime,language)
        except (httpx.HTTPError,ValueError,KeyError) as exc: raise HTTPException(502,'Speech recognition unavailable. Use text or try again.') from exc
        return {'text':text,'final':True,'latency_ms':(time.perf_counter()-tick)*1000}

    @routes.post('/speech')
    async def speech(body: VoiceTurn, request: Request, stream: bool = False):
        p=provider(request)
        service=request.app.state.conversations
        state=service.get(body.conversation_id)
        previous=service.repository.previous_turn(body.conversation_id,body.turn_id)
        if not previous: raise HTTPException(404,'Committed turn not found')
        answer=json.loads(previous['response'])
        if answer['state_version'] != state['state_version']: raise HTTPException(409,'Playback is stale')
        tick=time.perf_counter()
        if stream:
            iterator=p.stream_speech(answer['text'],answer['language'])
            try:
                first=await anext(iterator)
            except (httpx.HTTPError,ValueError,StopAsyncIteration) as exc:
                await iterator.aclose()
                raise HTTPException(502,'Voice output unavailable; text response is saved.') from exc
            first_byte_ms=(time.perf_counter()-tick)*1000
            if service.get(body.conversation_id)['state_version'] != state['state_version']:
                await iterator.aclose()
                raise HTTPException(409,'Playback is stale')

            async def audio_chunks():
                byte_count=0
                outcome='interrupted'
                try:
                    byte_count+=len(first)
                    yield first
                    async for chunk in iterator:
                        if service.get(body.conversation_id)['state_version'] != state['state_version']:
                            outcome='stale'
                            return
                        byte_count+=len(chunk)
                        yield chunk
                    outcome='complete'
                except (httpx.HTTPError,ValueError):
                    outcome='failed'
                    raise
                finally:
                    await iterator.aclose()
                    elapsed=(time.perf_counter()-tick)*1000
                    request.app.state.tracer.emit({'event_id':str(uuid4()),'conversation_id':body.conversation_id,
                        'turn_id':body.turn_id,'timestamp':now(),'type':'tts',
                        'latency':{'tts_first_byte_ms':first_byte_ms,'tts_ms':elapsed},
                        'bytes':byte_count,'state_version':state['state_version'],'streaming':True,
                        'outcome':outcome,'language':answer['language'],
                        'voice':p.speech_config.voice_for(answer['language'])})

            return StreamingResponse(audio_chunks(),media_type='audio/mpeg',headers={
                'X-TTS-First-Byte-Ms':str(first_byte_ms),'X-TTS-Streaming':'true',
                'Cache-Control':'no-store','X-Accel-Buffering':'no'})
        try: audio=await p.synthesize(answer['text'],answer['language'])
        except (httpx.HTTPError,ValueError) as exc: raise HTTPException(502,'Voice output unavailable; text response is saved.') from exc
        latency=(time.perf_counter()-tick)*1000
        if service.get(body.conversation_id)['state_version'] != state['state_version']: raise HTTPException(409,'Playback is stale')
        request.app.state.tracer.emit({'event_id':str(uuid4()),'conversation_id':body.conversation_id,'turn_id':body.turn_id,
            'timestamp':now(),'type':'tts','latency':{'tts_ms':latency,'total_voice_processing_ms':answer['latency']['total_text_ms']+(answer['latency']['stt_ms'] or 0)+latency},'bytes':len(audio),'state_version':state['state_version']})
        return Response(audio,media_type='audio/mpeg',headers={'X-TTS-Latency-Ms':str(latency),'Cache-Control':'no-store'})

    @routes.post('/playback')
    async def playback(body: PlaybackMetrics, request: Request):
        service=request.app.state.conversations
        state=service.get(body.conversation_id)
        previous=service.repository.previous_turn(body.conversation_id,body.turn_id)
        if not previous: raise HTTPException(404,'Committed turn not found')
        # Client telemetry is diagnostic only. It never advances the conversation.
        request.app.state.tracer.emit({'event_id':str(uuid4()),'conversation_id':body.conversation_id,
            'turn_id':body.turn_id,'timestamp':now(),'type':'tts_playback',
            'latency':body.model_dump(exclude={'conversation_id','turn_id','streaming'},exclude_none=True),
            'streaming':body.streaming,'state_version':state['state_version'],
            'measurement':'browser playing event; response-ready clock; client reported'})
        return {'recorded':True}

    @routes.post('/interruption')
    async def interruption(body: VoiceTurn,request: Request):
        state=request.app.state.conversations.get(body.conversation_id)
        request.app.state.tracer.emit({'event_id':str(uuid4()),'conversation_id':body.conversation_id,'turn_id':body.turn_id,
            'timestamp':now(),'type':'playback_stale','state_version':state['state_version']})
        return {'playback_stale':True,'state_version':state['state_version']}

    return routes
