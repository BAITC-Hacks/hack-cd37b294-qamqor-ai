import os
import httpx
from dotenv import dotenv_values
from app.catalog.loader import PROJECT_ROOT
from app.voice.config import SpeechConfig
from app.voice.normalization import normalize_speech


class OpenAIAudio:
    def __init__(self, settings, client):
        self.settings,self.client=settings,client
        values={**dotenv_values(PROJECT_ROOT/'.env'),**os.environ}
        self.key=values.get('CALLAI_VOICE_API_KEY') or settings.api_key
        self.base=values.get('CALLAI_VOICE_BASE_URL') or settings.base_url
        self.stt_model=values.get('CALLAI_STT_MODEL') or 'whisper-1'
        self.speech_config=SpeechConfig.from_values(values)
        self.tts_model=self.speech_config.model
        self.voice=self.speech_config.voice_ru
        self.configured=bool(self.key and values.get('CALLAI_VOICE_ENABLED','true').lower() not in {'false','0','no'})

    async def transcribe(self,audio,mime,language=None):
        extension={'audio/webm':'webm','audio/mp4':'mp4','audio/wav':'wav','audio/mpeg':'mp3','audio/ogg':'ogg'}.get(mime,'webm')
        response=await self.client.post(self.base+'/audio/transcriptions',headers={'Authorization':'Bearer '+self.key},
            data={'model':self.stt_model,'response_format':'json',**({'language':language} if language else {})},files={'file':('utterance.'+extension,audio,mime)},timeout=60)
        response.raise_for_status()
        text=response.json()['text'].strip()
        if not text: raise ValueError('No final speech recognized')
        return text

    def speech_payload(self, text, language):
        config=self.speech_config
        voice=config.voice_for(language)  # Only the committed final response chooses the voice.
        spoken=normalize_speech(text, language)
        if not spoken or len(spoken)>4096:
            raise ValueError('Speech text is empty or exceeds the provider limit; saved text is unchanged.')
        payload={'model':config.model,'voice':voice,'input':spoken,
                 'response_format':'mp3','speed':config.speed}
        if config.model not in {'tts-1','tts-1-hd'}:
            payload['instructions']=config.style_for(language)
        return payload

    async def stream_speech(self, text, language):
        """Yield decoded MP3 bytes as received; close upstream on cancellation."""
        async with self.client.stream('POST',self.base+'/audio/speech',
                headers={'Authorization':'Bearer '+self.key},
                json=self.speech_payload(text,language),timeout=60) as response:
            response.raise_for_status()
            received=False
            async for chunk in response.aiter_bytes():
                if chunk:
                    received=True
                    yield chunk
            if not received:
                raise ValueError('Empty audio')

    async def synthesize(self,text,language):
        # Preserve the existing complete-file interface for callers and fallback clients.
        return b''.join([chunk async for chunk in self.stream_speech(text,language)])
