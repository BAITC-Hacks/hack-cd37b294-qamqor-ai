"""Speech-only configuration. Never used by the router or response composer."""
from dataclasses import dataclass
import math


CALL_CENTER_STYLE = (
    'Read only the supplied text, without additions. Sound like a calm, professional '
    'insurance call-center specialist: warm but restrained, conversational and clear. '
    'Use natural sentence stress, short pauses at punctuation, and a steady moderate pace. '
    'Avoid a radio-announcer delivery, exaggerated emotion, and a mechanical sing-song rhythm.'
)
LANGUAGE_STYLE = {
    'ru': 'Speak natural Russian with Russian stress and pronunciation. Keep brief phrases fluid.',
    'kk': 'Speak natural Kazakh with Kazakh vowel harmony, stress, and pronunciation, '
          'not Russian phonetics. Clearly distinguish ә, ғ, қ, ң, ө, ұ, ү, һ, і. '
          'For embedded Russian words, preserve the words without translating or adding text.',
}


@dataclass(frozen=True)
class SpeechConfig:
    provider: str = 'openai'
    model: str = 'gpt-4o-mini-tts'
    voice_ru: str = 'coral'
    voice_kk: str = 'coral'
    speed: float = 1.0
    instructions: str = ''

    @classmethod
    def from_values(cls, values):
        config = cls(
            provider=values.get('TTS_PROVIDER') or 'openai',
            model=values.get('TTS_MODEL') or values.get('CALLAI_TTS_MODEL') or 'gpt-4o-mini-tts',
            voice_ru=values.get('TTS_VOICE_RU') or values.get('CALLAI_TTS_VOICE') or 'coral',
            voice_kk=values.get('TTS_VOICE_KK') or values.get('CALLAI_TTS_VOICE') or 'coral',
            speed=float(values.get('TTS_SPEED') or 1.0),
            instructions=values.get('TTS_INSTRUCTIONS') or '',
        )
        if config.provider != 'openai':
            raise ValueError('TTS_PROVIDER must be openai (the existing OpenAI-compatible audio service).')
        if not math.isfinite(config.speed) or not 0.25 <= config.speed <= 4.0:
            raise ValueError('TTS_SPEED must be a finite number between 0.25 and 4.0.')
        return config

    def voice_for(self, language):
        if language not in LANGUAGE_STYLE:
            raise ValueError('Speech requires the final response language: ru or kk.')
        return self.voice_kk if language == 'kk' else self.voice_ru

    def style_for(self, language):
        self.voice_for(language)
        return ' '.join(filter(None, (CALL_CENTER_STYLE, LANGUAGE_STYLE[language], self.instructions)))

    def public(self):
        return {'provider': self.provider, 'model': self.model, 'voice_ru': self.voice_ru,
                'voice_kk': self.voice_kk, 'speed': self.speed, 'format': 'mp3',
                'sample_rate': 'provider default; no API override', 'streaming_supported': True}
