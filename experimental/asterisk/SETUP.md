# Experimental Asterisk AudioSocket adapter

This is an opt-in transport experiment. A real Asterisk call has **not** been executed or verified on this workstation. It is not a completed SIP/PSTN feature or a replacement for the working Web Voice demo.

The main application startup, its Docker files, routing core, state/action logic and voice API remain separate. The bridge calls the existing HTTP session, STT, chat and TTS endpoints. `TELEPHONY_ENABLED` defaults to `false`; the standalone bridge exits before opening a socket or requiring optional tools. Asterisk is in a separate Compose file under profile `telephony`, with its own disabled-by-default entrypoint and `restart: "no"`.

## Scope and transport

The experiment uses the Asterisk **AudioSocket dialplan application**. ARI is not used and no ARI credentials are required. HTTP/ARI and AMI are disabled; no SIP endpoint, SIP account, outbound trunk, public telephone number or published Docker port is configured.

AudioSocket frames contain a one-byte type, two-byte big-endian payload length and payload. The adapter's selected format is type `0x10`: mono signed 16-bit little-endian PCM at 8 kHz. The connection begins with a binary 16-byte UUID (type `0x01`). `Answer()` precedes `AudioSocket()` in the supplied dialplan. These are the official [protocol](https://docs.asterisk.org/Configuration/Channel-Drivers/AudioSocket/) and [dialplan application](https://docs.asterisk.org/Asterisk_22_Documentation/API_Documentation/Dialplan_Applications/AudioSocket/) contracts.

The application has a roughly two-second inactivity timeout in [Asterisk 22.11.0 source](https://github.com/asterisk/asterisk/blob/22.11.0/apps/app_audiosocket.c). The bridge must continue sending 20 ms silence frames while awaiting STT, chat or TTS. This is transport keepalive audio, not a new user utterance.

The Dockerfile builds the pinned Asterisk **22.11.0** source release on the official Debian base. Its SHA-256 is taken from the [official release checksum](https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-22.11.0.sha256):

```text
3bd5ee040509a3d3cd9b1ba9520c18e6ec0a7e7981ca68c457dcd36ba3c54d94
```

The source archive will be checked during an explicitly requested image build. No prebuilt third-party Asterisk image is used. The image itself has not been built here.

## Prerequisites for a future local call

1. Keep the existing Halyk CallAI backend running at `http://127.0.0.1:8000` with its ordinary voice configuration. No API key is passed to Asterisk or copied into its image.
2. Make `ffmpeg` available to the standalone Python bridge, or set `TELEPHONY_FFMPEG` to its existing executable path. No system dependency is installed automatically.
3. Start Docker Desktop's Linux engine manually if you choose to run this experiment. Inspection on 2026-09-23 found Docker CLI 29.5.2 and Compose v5.1.4, but the engine was unavailable (`dockerDesktopLinuxEngine` pipe not found).
4. The optional Compose file uses **host networking** so that the bridge can keep binding to `127.0.0.1:9092`. Native Linux supports this directly. Docker Desktop requires version 4.34+ and its explicit **Enable host networking** setting. Nothing in this project changes Docker settings. If host networking is unavailable, do not broaden the main backend or bridge bind to work around it; leave this experiment disabled. See [Docker's host networking prerequisites](https://docs.docker.com/engine/network/drivers/host/).

Host networking is used only after activating the separate profile. Asterisk has no configured TCP/UDP server listener; its CLI uses a Unix-domain socket inside the container. With the profile omitted, this Compose file has no active service.

## Inspect configuration without starting anything

Run from the `halyk-callai` directory:

```powershell
docker compose -f experimental/asterisk/deploy/compose.yaml config --services
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony config --quiet
```

The first command should list no active services. The second only validates Compose syntax. Neither builds an image, starts Asterisk nor proves that its modules/dialplan work.

## Explicit local-only validation procedure

These steps are instructions for a future validation, **not executed results**. The supplied fixture call stays entirely within Asterisk Local channels and the loopback bridge; it does not dial a person or an external number.

The standalone bridge reads **process environment variables only**. It does not automatically load the project's `.env` file. Set the optional variables in the terminal that launches the bridge; the existing web backend continues using its own configuration.

In a separate PowerShell terminal at the project root, start the optional bridge:

```powershell
$env:TELEPHONY_ENABLED = 'true'
$env:TELEPHONY_HOST = '127.0.0.1'
$env:TELEPHONY_PORT = '9092'
$env:TELEPHONY_BACKEND_URL = 'http://127.0.0.1:8000'
$env:TELEPHONY_LANGUAGE = 'ru'
$env:TELEPHONY_MAX_CALLS = '1'
$env:TELEPHONY_API_TIMEOUT_SECONDS = '120'
# Optional when ffmpeg is not on PATH:
# $env:TELEPHONY_FFMPEG = 'C:\path\to\ffmpeg.exe'
.\.venv\Scripts\python.exe -m experimental.asterisk
```

In another terminal, convert a previously generated **caller** fixture to raw 8 kHz PCM. This command expects an existing `ffmpeg` executable and does not generate new speech:

```powershell
ffmpeg -n -i evaluation/voice-probe/ru-input.mp3 -ac 1 -ar 8000 -f s16le experimental/asterisk/deploy/fixtures/input.sln
```

`-n` prevents accidentally overwriting a fixture. For a KK pass, use a separately chosen KK fixture and set the bridge's response language appropriately before restarting only the optional bridge. The supplied `kk-input.mp3` is synthetic test audio, not proof of live caller quality.

Only after the prerequisites are satisfied, opt into the Asterisk image and process:

```powershell
$env:TELEPHONY_ENABLED = 'true'
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony up --build -d
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony exec asterisk asterisk -rx 'core show application AudioSocket'
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony exec asterisk asterisk -rx 'dialplan show callai-local'
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony exec asterisk asterisk -rx 'module show like res_clioriginate'
```

Check that the AudioSocket application and dialplan exist before originating one Local-channel probe:

```powershell
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony exec asterisk asterisk -rx 'channel originate Local/7000@callai-local/n extension s@callai-fixture'
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony logs --tail 100 asterisk
```

The `Local/.../n` path keeps both Local legs available. One leg runs `AudioSocket`, while the other plays `/fixtures/input.sln` as caller audio and waits for the assistant. No SIP registration is involved. Asterisk's [Local-channel documentation](https://docs.asterisk.org/Configuration/Channel-Drivers/Local-Channel/Local-Channel-Examples/Using-Callfiles-and-Local-Channels/) describes this in-process call mechanism.

Recordings are written to the isolated Compose volume at `/recordings`: `mixed-*.wav`, `assistant-*.wav` and `caller-*.wav`. Collect a recording for listening with `docker compose ... cp asterisk:/recordings <a-chosen-local-output-directory>`. Do not claim a call passed from the CLI accepting the originate command alone. A successful validation must show the AudioSocket UUID, final STT text, one committed chat turn, generated response audio, clean hangup, and a playable received-audio recording. Verify that the main text/Web Voice demo still works afterward.

To stop the optional process, use Ctrl+C in its bridge terminal and:

```powershell
docker compose -f experimental/asterisk/deploy/compose.yaml --profile telephony down
$env:TELEPHONY_ENABLED = 'false'
```

`down` here affects only the separate experimental Compose project; it preserves the recordings volume. The main application has no dependency on it.

## Remaining validation limits

- Utterance endpointing uses an energy threshold and **700 ms of silence**. It needs validation with actual caller audio, pauses and background noise; it is not a validated telephone speech detector.
- Oversized utterances are discarded. The adapter does not route a truncated or intermediate portion as a final user turn.
- Action confirmation over the phone is not implemented. DTMF digits and affirmative speech never synthesize `confirm_operation_id`; required action confirmations must use the existing Web UI.
- Final utterances are processed sequentially per call through the shared backend APIs, preserving the order of chat state updates. An ambiguous API failure or timeout is never automatically retried; the current call is closed rather than risking duplicate work.
- Docker image build, Asterisk module load, dialplan execution and Docker Desktop loopback reachability have not been executed on this host.
- This Local-file procedure does not verify a live microphone, physical handset, SIP/RTP path, packet loss or public telephone network.
- SIP/PSTN and ARI are deliberately not configured and must not be described as supported production features.
- Telephone-band 8 kHz audio can reduce recognition and pronunciation quality compared with Web Voice; the local call must be measured before making a demo claim.
