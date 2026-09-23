# Experimental Asterisk status — 2026-09-23

**Web demo verified; telephony disabled. Actual Asterisk call not verified.**

Checkpoint before implementation: `885d368a029721dbdbf4f15582930e605d479125`
(`checkpoint before asterisk demo integration`). The working tree was clean, so
the checkpoint is an empty commit.

## Implementation boundary

- The adapter is a standalone process under `experimental/asterisk/`. The main
  backend does not import, initialize or wait for it, even when the flag is true.
- `.env.example` and local, ignored `.env` contain `TELEPHONY_ENABLED=false`.
  A missing flag also disables the adapter. Its CLI reads process environment;
  it does not automatically load `.env`.
- The bridge calls existing session, final STT, chat, committed-turn TTS and
  interruption HTTP APIs. It adds no endpoint, provider or routing logic.
- AudioSocket framing, energy endpointing, ordered turns, paced PCM/silence and
  output interruption are implemented. Optional ffmpeg decodes existing MP3
  responses; it is never needed by Web Voice.
- Asterisk has its own Compose project and explicit `telephony` profile. The
  main Compose file has no telephony service or dependency. ARI/SIP/PSTN are not
  configured. No phone number is called.
- No phone confirmation support: speech and DTMF never manufacture a
  `confirm_operation_id`. Actions needing explicit confirmation remain pending
  for the existing Web UI.

## Executed verification

| Check | Executed result |
| --- | --- |
| Original backend tests before adapter | 202 passed |
| Original player tests before adapter | 9 passed |
| Final `python -m pytest backend/tests experimental/asterisk/tests -q --junitxml=evaluation/telephony/tests-final.xml` | **262 passed**, 18.25 s |
| Final frontend `npm test` | **9 passed** |
| Experimental tests within the 262 total | **60 passed**: 28 audio/protocol, 13 isolation, 19 HTTP/bridge |
| Main Compose `config --quiet` | Passed |
| Optional profile Compose `config --quiet` | Passed |
| Optional Compose without profile | No active services |
| Entrypoint with flag missing / false | Exit 0, disabled; no runtime imports or network |
| Entrypoint enabled with missing decoder | Exit 0, unavailable/disabled; main backend remains available |
| Optional shell entrypoint syntax and disabled mode | Passed |
| `git diff --check` | Passed |

The bridge tests use real short-lived loopback TCP connections and mocked HTTP
provider responses/decoding. They verify silence-completed utterances, ordered
state versions, 320-byte paced output, barge-in, stale-audio suppression,
disconnect, malformed frames, call limit and isolated failures. They are not
evidence of a real PBX call. Process-isolation tests block optional imports and
exercise core startup, health, sessions, voice status and supervisor routes with
the flag absent, false and true.

An intermediate run (`tests-stage1.xml`) had 242 passed and one Golden lock
failure while another authorized task was updating the dataset path and matching
checksum. Its completed change and the final combined suite pass. No routing
test, evaluation logic or gold label was changed for this adapter.

### Live Web Voice regression

Existing synthetic caller MP3 fixtures were sent through the running backend
using real STT, `gpt-6-astra` routing and TTS API requests. This was not a live
microphone test or an official baseline rerun.

| Language | Path | Result | Output audio | Total client time |
| --- | --- | --- | --- | --- |
| RU | STT → chat → buffered TTS | PASS | 189,696 bytes | 15.83 s |
| KK | STT → chat → streamed TTS | PASS | 199,296 bytes, 98 received chunks | 13.26 s |

Both answers cite the existing office data, retain the selected language and
commit state version 1. The saved session and supervisor endpoint were checked.
Voice remains `marin` for RU and KK, speed 1.0. Backend health was OK before and
after; `http://127.0.0.1:3000/` returned HTTP 200. These two observations are
regression checks, not a latency distribution or pronunciation assessment.

Evidence:

- [Final pytest report](../../evaluation/telephony/tests-final.xml)
- [Entrypoint checks](../../evaluation/telephony/entrypoint-checks.json)
- [Live Web Voice results](../../evaluation/telephony/web-smoke/results.json)
- [RU response](../../evaluation/telephony/web-smoke/ru-response.mp3)
- [KK response](../../evaluation/telephony/web-smoke/kk-response.mp3)
- [File integrity report](../../evaluation/telephony/integrity.json)

## File ownership and concurrent work

This task adds `experimental/__init__.py`, the `experimental/asterisk/` package,
tests and deployment instructions, plus verification artifacts in
`evaluation/telephony/`. Its only tracked configuration edit is the three-line
disabled-telephony addition to `.env.example`; local `.env` is ignored by Git.

A separate user-authorized task committed `2113a49` during this work: README,
the built-in dataset default and Docker mount, matching loader lock hash, and
the Halyk logo. Those changes were preserved. Of 70 files snapshotted before
telephony work, 64 remain byte-identical; six differ due to that separate commit.
The checked main application files match the current HEAD. Telephony did not
modify Web Voice, router, policy, backend startup, API contracts or root Compose.

## Blockers and next step

Docker CLI and Compose exist, but the Docker Linux engine is unavailable.
`ffmpeg` was not found on PATH. No Docker image build, Asterisk module loading,
dialplan execution, real conversion or Asterisk call has been executed. Host
networking prerequisites also remain unverified. No such capability is claimed
in the main README.

Keep `TELEPHONY_ENABLED=false`. When the prerequisites are available, follow
[SETUP.md](SETUP.md) for one Local-channel fixture call and inspect its received
audio recording. Preserve the existing backend binding and Web Voice pipeline.
SIP and external calling require separate work after that local call succeeds.
