"""Generate one fixed, comparable audition set. No router, STT, or policy calls."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

import httpx
from app.config.settings import Settings
from app.voice.providers import OpenAIAudio


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'frontend/public/voice_samples'
CANDIDATES = ('coral', 'marin', 'cedar')
PHRASES = (
    ('ru', 'greeting', 'Здравствуйте. Я помогу вам разобраться с вашим страховым полисом.'),
    ('ru', 'payment', 'Платёж вижу. Сейчас уточню статус оформления полиса.'),
    ('kk', 'greeting', 'Сәлеметсіз бе. Сақтандыру полисі бойынша көмектесуге дайынмын.'),
    ('kk', 'payment', 'Төлем туралы ақпаратты көріп тұрмын. Қазір полистің мәртебесін тексеремін.'),
    ('kk', 'mixed', 'Ақша списали, бірақ полис келмеді.'),
)


def mp3_properties(data):
    offset = 0
    if data[:3] == b'ID3' and len(data) >= 10:
        offset = 10 + sum((data[6+i] & 127) << (21-7*i) for i in range(4))
    rates = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}
    for i in range(offset, len(data)-3):
        header = int.from_bytes(data[i:i+4], 'big')
        version, layer, bitrate, rate = (header >> 19) & 3, (header >> 17) & 3, (header >> 12) & 15, (header >> 10) & 3
        if header >> 21 == 2047 and version in rates and layer == 1 and bitrate not in (0,15) and rate < 3:
            return {'sample_rate_hz': rates[version][rate], 'channels': 1 if (header >> 6) & 3 == 3 else 2}
    raise ValueError('No valid MP3 frame header')


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / 'manifest.json'
    if manifest_path.exists():
        raise SystemExit('Comparison set already exists. Audition it; do not regenerate or change candidates automatically.')
    settings = Settings.load()
    settings.require_api_key()
    limit = asyncio.Semaphore(2)
    async with httpx.AsyncClient() as client:
        base = OpenAIAudio(settings, client)
        if not base.configured:
            raise SystemExit('Voice credentials are not configured or voice is disabled.')

        async def generate(index, voice, language, name, phrase):
            async with limit:
                provider = OpenAIAudio(settings, client)
                provider.speech_config = replace(base.speech_config, voice_ru=voice, voice_kk=voice, speed=1.0)
                payload = provider.speech_payload(phrase, language)
                record = {'candidate': index, 'voice': voice, 'language': language, 'phrase_id': name,
                          'text': phrase, 'spoken_text': payload['input'], 'model': payload['model'],
                          'speed': payload['speed'], 'instructions': payload.get('instructions'),
                          'file': f'{language}_{index:02d}_{name}.mp3'}
                started, first, chunks = time.perf_counter(), None, []
                try:
                    async for chunk in provider.stream_speech(phrase, language):
                        if first is None:
                            first = (time.perf_counter()-started)*1000
                        chunks.append(chunk)
                    complete = (time.perf_counter()-started)*1000
                    audio = b''.join(chunks)
                    properties = mp3_properties(audio)
                    (OUTPUT / record['file']).write_bytes(audio)
                    record.update(status='PASS', first_byte_ms=round(first,2), complete_tts_ms=round(complete,2),
                                  audio_bytes=len(audio), sha256=hashlib.sha256(audio).hexdigest(), **properties)
                except (httpx.HTTPError, ValueError) as exc:
                    record.update(status='FAIL', error_type=type(exc).__name__)
                    if isinstance(exc, httpx.HTTPStatusError):
                        record['http_status'] = exc.response.status_code
                print(json.dumps({k:record[k] for k in ('file','status','first_byte_ms','complete_tts_ms','error_type','http_status') if k in record}), flush=True)
                return record

        samples = await asyncio.gather(*(generate(i,voice,language,name,phrase)
            for i,voice in enumerate(CANDIDATES,1) for language,name,phrase in PHRASES))
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'provider': base.speech_config.provider,
                'candidates': list(CANDIDATES), 'sample_count': len(samples),
                'measurement': 'Monotonic time from ready fixed phrase before provider request; excludes queue wait. '
                               'First byte and complete download measured, browser playback measured separately.',
                'selection': 'pending human audition; application defaults remain coral', 'samples': samples}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(ROOT/'scripts/voice_comparison.html', OUTPUT/'index.html')
    if any(row['status'] != 'PASS' for row in samples):
        raise SystemExit('Some samples failed; inspect manifest before any retry.')


if __name__ == '__main__':
    asyncio.run(main())
