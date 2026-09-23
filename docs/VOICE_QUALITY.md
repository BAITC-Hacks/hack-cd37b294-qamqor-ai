# Voice quality pass — 2026-09-23

Technical checks passed. The user subsequently selected **marin for both RU and KK**, speed **1.0**. This choice is now applied to the running application. The comparison and measurements below preserve the original audition-stage evidence.

Open the running app at http://127.0.0.1:3000/voice_samples/index.html. It has 15 saved samples, three candidates for each language, identical phrases/settings, and a local RU/KK choice with downloadable `.env` settings. Selection does not edit application configuration. All three candidates remain available; no further candidate generation or tuning was performed after this set.

## Audit and current configuration

| Field | Before | After |
|---|---|---|
| Provider | OpenAI, api.openai.com | Same |
| Model | gpt-4o-mini-tts | Same; `TTS_MODEL` override |
| Voice | coral for both languages | coral defaults retained; separate `TTS_VOICE_RU` / `TTS_VOICE_KK` |
| Language | Committed answer language | Same; no independent TTS language detection |
| Speed | Provider default | Explicit 1.0; `TTS_SPEED` override |
| Audio | MP3, 24 kHz mono in prior files | MP3, 24 kHz mono verified in all 15 new files |
| Sample-rate setting | None | None; this API does not expose a sample-rate override |
| Instructions | One short clarity instruction | Shared calm, warm, restrained call-center guidance plus RU/KK pronunciation guidance |
| Preprocessing | None | Deterministic speech-only normalizer |
| Delivery | Entire MP3 buffered at server and browser | MP3 stream through MediaSource; full-file fallback |

New environment variables: `TTS_PROVIDER=openai`, `TTS_MODEL`, `TTS_VOICE_RU`, `TTS_VOICE_KK`, `TTS_SPEED`, `TTS_INSTRUCTIONS`. Existing `CALLAI_TTS_MODEL` / `CALLAI_TTS_VOICE` remain fallbacks. Credentials and STT configuration are unchanged. The actual `.env` was not modified in this pass.

The final stored response determines both voice and language instruction. Only its speech representation changes; conversation history, router inputs, response composition, source data and state/action semantics do not change. No additional LLM rewriting request is introduced.

## Human audition

| Candidate | RU | KK | Speed |
|---|---|---|---|
| 01 | coral | coral | 1.0 |
| 02 | marin | marin | 1.0 |
| 03 | cedar | cedar | 1.0 |

Suggested first auditions: RU **marin**, KK **cedar**, both `gpt-4o-mini-tts`, speed 1.0, the included language-specific style. These are provisional starting points, not measured pronunciation winners. The [official TTS guide](https://developers.openai.com/api/docs/guides/text-to-speech) recommends marin/cedar for quality and lists Russian/Kazakh support, while noting that voices are optimized for English. A native Kazakh listener must judge pronunciation. The [Speech API reference](https://developers.openai.com/api/reference/cli/resources/audio/subresources/speech/methods/create) documents instructions, speed and streamed audio.

The exact five requested phrases were each generated with all three voices. The mixed phrase uses final language `kk` deliberately; no detection or translation is performed. All resulting files and their inputs, normalized inputs, instructions, sizes, hashes and measurements are in `frontend/public/voice_samples/manifest.json`.

## Executed measurements

Actual browser checks replayed existing committed RU/KK office answers without calling `/api/chat` or rerunning the router. Current application voice was coral, speed 1.0. These are **one completed browser run per language**, not distribution estimates. The clock begins when replay of the already-ready answer is requested. Normal conversation playback uses the receipt of the final chat response as its origin.

| Language | Ready → first browser byte | Ready → browser `playing` | Ready → complete download | Backend first byte | Backend complete |
|---|---:|---:|---:|---:|---:|
| RU | 1364.80 ms | 1380.10 ms | 2667.20 ms | 1337.93 ms | 2653.72 ms |
| KK | 903.00 ms | 1112.30 ms | 2630.00 ms | 885.99 ms | 2619.51 ms |

Both began playback before the stream finished. `playing` is a browser event proxy; it does not certify physical speaker output or subjective sound quality. Complete download excludes the remaining duration of speech playback.

The fixed comparison set has 6 RU and 9 KK files (including the 3 mixed samples). Means across those short samples: RU first byte **1376.11 ms**, complete **2019.95 ms**; KK first byte **1047.99 ms**, complete **1710.91 ms**. These measure provider generation/download from the ready phrase, exclude local concurrency-queue wait, and are separate from the office-answer browser measurements.

Browser interruption was exercised after `playing` while stream completion was still null. The backend recorded interrupted streams and the browser stopped playback/loading. Both existing conversations remained at state version 1. Evidence: `evaluation/voice-quality-playback.json`.

## Normalization and compatibility

- Decimal values retain fractional digits and trailing zeros; phone numbers, leading zeros and recognized policy identifiers retain every digit.
- Valid dates and clock ranges become explicit speech notation. Unknown/ambiguous number formats, emails and URLs are preserved without guessing.
- RU/KK numbers, currency, percentages, known abbreviations and the actual Almaty/Abai/Mon-Fri/Sat office tokens are supported.
- Markdown and recognized internal scenario/trace metadata are removed from speech. No scenario code is intentionally spoken.
- No facts, obligations or claims are added. The exact final answer stays stored and displayed.
- Normalized input over 4096 characters is rejected for TTS, leaving the saved text available; no truncation or untested chunk stitching.
- Existing `POST /api/voice/speech` still returns a complete MP3 with `X-TTS-Latency-Ms`. New frontend requests `?stream=true`; its first-byte header is separate from completion telemetry.
- Streaming preserves stale-turn checks, closes the upstream iterator on cancellation, and uses the existing blob fallback where MP3 MediaSource is unavailable.

## Tests actually executed

- Full backend suite: **192 passed, 0 failed**, `evaluation/voice-quality-tests.xml`.
- Included: 31 normalizer tests, 30 new voice configuration/stream/telemetry/failure tests, existing voice and backend regression tests.
- Frontend playback suite: **9 passed, 0 failed**, including progressive playback before EOF, cancellation, stale callbacks, fallback and decoding/empty-audio failure paths.
- Next.js production build: passed; `scripts/run.ps1 demo` rebuilt and restarted both services successfully.
- `compileall` for voice modules/comparison script: passed. `pip check`: passed.
- Real TTS comparison generation: **15/15 succeeded**, saved MP3 frame headers and SHA256 hashes verified.
- Real RU and KK browser streaming playback: passed; interruption: passed. Comparison page rendered and exposes all 15 audio controls.
- Golden L2: **16/16 protected SHA256 hashes unchanged**. All preexisting nonvoice backend files unchanged. `evaluation/voice-quality-integrity.json` records the check.
- No new routing inference, official evaluation, optimization or synthetic training corpus generation was run.

## Files changed in this pass

Existing source/configuration:

- `.env.example`
- `backend/app/voice/providers.py`
- `backend/app/voice/routes.py`
- `frontend/app/page.tsx` (voice output/playback handling only)
- `frontend/lib/playback.mjs`
- `frontend/tests/playback.test.mjs`
- `BUILD_LOG.md` (this pass record)

New source/tests/documentation:

- `backend/app/voice/config.py`
- `backend/app/voice/normalization.py`
- `backend/tests/integration/test_voice_quality.py`
- `backend/tests/unit/test_speech_normalization.py`
- `scripts/compare_voices.py`
- `scripts/voice_comparison.html`
- `frontend/scripts/build-playback-probe.mjs`
- `docs/VOICE_QUALITY.md`

Generated review/evidence files:

- `frontend/public/voice_samples/index.html`, `playback-check.html`, `playback.mjs`, `manifest.json`
- `frontend/public/voice_samples/ru_01_greeting.mp3`, `ru_01_payment.mp3`, `ru_02_greeting.mp3`, `ru_02_payment.mp3`, `ru_03_greeting.mp3`, `ru_03_payment.mp3`
- `frontend/public/voice_samples/kk_01_greeting.mp3`, `kk_01_payment.mp3`, `kk_01_mixed.mp3`, `kk_02_greeting.mp3`, `kk_02_payment.mp3`, `kk_02_mixed.mp3`, `kk_03_greeting.mp3`, `kk_03_payment.mp3`, `kk_03_mixed.mp3`
- `evaluation/voice-quality-before.json`, `voice-quality-integrity.json`, `voice-quality-playback.json`, `voice-quality-tests.xml`

The generator refuses to overwrite an existing manifest. The playback probe generator only copies the production player and reads previously committed demo turn IDs. No final voice choice has been applied.

## 2026-09-23 — Human voice selection

The user selected **marin for both Russian and Kazakh**, retaining speed **1.0**. This supersedes the pending-choice statements and provisional audition suggestions above. Selected settings are `TTS_VOICE_RU=marin`, `TTS_VOICE_KK=marin`, and `TTS_SPEED=1.0`; application configuration is being updated through local `.env` and `.env.example`, with runtime verification recorded separately.

No new samples or evaluations were generated for this selection. The browser latency measurements above remain historical **coral** measurements; they are not marin results. The saved comparison set remains unchanged.

## Kazakh time correction after human feedback

The original range formatter kept numeric clocks for the TTS model to interpret. It now spells valid KK ranges explicitly: `09:00-18:00` → `сағат тоғыздан он сегізге дейін`; `10:00-15:00` → `сағат оннан он беске дейін`. Minutes are preserved without rounding, and an existing `сағат` label is not duplicated. The time constructions were checked against the teaching examples at https://www.soyle.kz/file/download/37 and the whole-hour usage at https://www.gov.kz/memleket/entities/adilet-zhmb/press/news/details/1036681. This is a speech-only correction; canonical answer text, source hours and marin selection stay unchanged.

Validation: 74 focused tests passed. One real marin Kazakh TTS request succeeded after backend restart. Saved sample: `evaluation/voice-time-fix/kk-office-marin.mp3`; exact input, old/new spoken text and latency: `evaluation/voice-time-fix/normalization.json`. No audible improvement is asserted before human listening. Golden hashes: 16/16 unchanged.
