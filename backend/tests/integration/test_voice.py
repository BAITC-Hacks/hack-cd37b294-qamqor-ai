import asyncio
import json
from unittest.mock import AsyncMock
import httpx
from app.main import create_app
from app.config.settings import Settings
from app.voice.pipeline import FinalUtteranceAdapter


def test_disabled_voice_preserves_text_and_supervisor(tmp_path,monkeypatch):
    monkeypatch.setenv('CALLAI_VOICE_ENABLED','false')
    async def run():
        app=create_app(Settings(api_key=''),database_path=tmp_path/'db.sqlite')
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as c:
                assert (await c.get('/api/voice/status')).json()['configured'] is False
                assert (await c.post('/api/voice/transcribe',content=b'x'*100,headers={'Content-Type':'audio/webm'})).status_code==503
                assert (await c.post('/api/session',json={'language':'kk'})).status_code==200
                assert (await c.get('/api/supervisor/events')).status_code==200
    asyncio.run(run())


def test_final_utterances_only():
    async def run():
        service=AsyncMock();adapter=FinalUtteranceAdapter(service)
        assert await adapter.process('session','turn','partial',final=False) is None
        service.chat.assert_not_called()
        await adapter.process('session','turn','final',final=True)
        service.chat.assert_awaited_once()
        assert service.chat.call_args.args[0].input_mode=='voice'
    asyncio.run(run())


def test_audio_api_and_interruption_leave_committed_state(tmp_path,monkeypatch):
    monkeypatch.setenv('CALLAI_VOICE_ENABLED','true')
    def handler(request):
        if request.url.path.endswith('transcriptions'):return httpx.Response(200,json={'text':'Где офис?'})
        return httpx.Response(200,content=b'ID3'+b'a'*100,headers={'Content-Type':'audio/mpeg'})
    async def run():
        app=create_app(Settings(api_key='fixture'),httpx.MockTransport(handler),database_path=tmp_path/'db.sqlite')
        async with app.router.lifespan_context(app):
            service=app.state.conversations;s=service.create();s['state_version']=1
            answer={'text':'Офис в Алматы','language':'ru','state_version':1,'latency':{'total_text_ms':100,'stt_ms':10}}
            service.repository.save(s,('t1','request',json.dumps(answer)))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as c:
                transcript=await c.post('/api/voice/transcribe',content=b'a'*100,headers={'Content-Type':'audio/webm;codecs=opus'})
                assert transcript.json()['final'] is True
                body={'conversation_id':s['conversation_id'],'turn_id':'t1'}
                speech=await c.post('/api/voice/speech',json=body);assert speech.status_code==200 and speech.content.startswith(b'ID3')
                assert (await c.post('/api/voice/interruption',json=body)).json()['playback_stale']
                assert service.get(s['conversation_id'])==s
                s['state_version']=2;service.repository.save(s)
                assert (await c.post('/api/voice/speech',json=body)).status_code==409
    asyncio.run(run())
