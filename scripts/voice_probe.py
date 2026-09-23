"""Live provider probe using generated RU/KK audio; does not claim a human-microphone test."""
import asyncio
import json
from pathlib import Path
import time
from uuid import uuid4
import httpx
from app.config.settings import Settings
from app.voice.providers import OpenAIAudio


async def main():
    root=Path('evaluation/voice-probe');root.mkdir(parents=True,exist_ok=True)
    results=[]
    async with httpx.AsyncClient(timeout=180) as client:
        provider=OpenAIAudio(Settings.load(),client)
        for language,text in [('ru','Где находится ваш офис в Алматы?'),('kk','Алматыдағы кеңсеңіз қайда орналасқан?')]:
            record={'language':language,'input_text':text,'source':'synthetic TTS fixture, not live microphone'}
            try:
                fixture=await provider.synthesize(text,language);(root/f'{language}-input.mp3').write_bytes(fixture)
                start=time.perf_counter()
                stt=await client.post('http://127.0.0.1:8000/api/voice/transcribe',params={'language':language},content=fixture,headers={'Content-Type':'audio/mpeg'});stt.raise_for_status();transcript=stt.json();record['stt']=transcript
                s=await client.post('http://127.0.0.1:8000/api/session',json={'language':language});s.raise_for_status();sid=s.json()['conversation_id'];turn=str(uuid4())
                r=await client.post('http://127.0.0.1:8000/api/chat',json={'conversation_id':sid,'turn_id':turn,'text':transcript['text'],'language':language,'input_mode':'voice','stt_latency_ms':transcript['latency_ms']});r.raise_for_status();record['chat']=r.json()
                tts=await client.post('http://127.0.0.1:8000/api/voice/speech',json={'conversation_id':sid,'turn_id':turn});tts.raise_for_status()
                (root/f'{language}-response.mp3').write_bytes(tts.content)
                record.update(status='PASS',output_audio_bytes=len(tts.content),tts_ms=float(tts.headers['X-TTS-Latency-Ms']),total_voice_processing_ms=(time.perf_counter()-start)*1000)
                assert r.json()['language']==language and r.json()['citations']
            except Exception as exc:record.update(status='FAIL',error=type(exc).__name__+': '+str(exc))
            results.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
            (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(r['status']=='PASS' for r in results) else 1

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
