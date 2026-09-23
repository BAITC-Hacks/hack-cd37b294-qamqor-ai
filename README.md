# Halyk CallAI — B0–B5 routing core

Locked specification: `../BUILD_SPEC.md`. Canonical data remains untouched in `../case_2/voice_router_dataset/`; no copied gold or modified evaluator. The compiler reads definitions, slots and boundary rules, never dev labels/examples.

## Run on Windows

From this directory:

```powershell
.\scripts\run.ps1
```

Creates a Python 3.12+ virtual environment, installs the project with the tested dependency constraints in `requirements.lock`, starts FastAPI on `http://127.0.0.1:8000`. Interactive API docs: `/docs`. No API key is necessary for `/health`, validation, compilation or offline tests.

For real inference copy `.env.example` to `.env` and set `OPENAI_API_KEY` locally. Do not commit or send the key in chat. The default model remains **gpt-6-astra**; no silent provider/model substitution. `/ready` reports configuration presence, not verified API access.

```powershell
.\scripts\run.ps1 validate
.\scripts\run.ps1 compile
.\scripts\run.ps1 test
.\scripts\run.ps1 baseline
```

After installation, equivalent commands are `python scripts/validate_dataset.py`, `python -m app.catalog.compiler`, `python -m pytest -q`, `python evaluation/run_official.py` using the venv Python. Docker alternative: `docker compose up --build` (not yet executed here).

## Implemented

- B0: dataset validator; canonical references, identity links, official input structure and source hashes. D01's 12 messages are a warning, never edited.
- B1: deterministic complete compact catalog: 40 business scenarios, 3 system intents, 63 directional rules, 43 slots. Gold and example utterances excluded from prompt.
- B2: strict Pydantic contracts, canonical enums, attributable evidence, exact source quotations, slot formats, stale-evidence rejection.
- B3: real OpenAI Responses HTTP adapter with strict JSON schema. One low-effort call and at most one medium-effort repair/reanalysis. Low confidence alone never retries. Technical errors are not fabricated SYS intents.
- B4: deterministic policy: urgent-first, clarify for missing facts, preserved task context, switch/restore, OOD, goodbye and explicit operator requests. Routing does not authorize backend execution.
- B5 runner: reads all official utterances; sends only text and empty initial state; records real outputs; executes original `evaluate.py` only after the full run; writes metrics/error taxonomy, source/code/prompt hashes and measured latency.

Internal endpoint `POST /api/route` accepts `RouterInput` and returns validated proposal and policy decision. No persistence or mock action execution is claimed here. ConversationService, the specified session/chat/supervisor APIs, action executor, frontend and voice remain B6+.

## Evaluation honesty

**MEASURED, 2026-09-23:** two complete live runs on the unchanged official 104-example development set. Latest run `20260923T095132_960641Z`: primary **104/104**, full-match **104/104**, multi-intent recall **26/26**. RU 52/52, KK 45/45, mixed 7/7. Zero final schema, API or system-intent failures; one schema-repair retry. Mean router latency **9347.58 ms**, p95 **13230.12 ms**. This reused dev set is not an independent hidden-test result.

Initial run: primary 100/104, full-match 99/104, recall 23/26. Measured failures were corrected without changing gold or the scorer. See [run comparison](evaluation/BASELINE_NOTES.md), [latest report](evaluation/results/baseline.md) and [official scorer output](evaluation/results/20260923T095132_960641Z/official_stdout.txt). B0–B5 is executed; full product completion remains B6+.

`python evaluation/run_boundary_probe.py` separately tests the ambiguous payment/policy example from BUILD_SPEC section 13 with live inference. Executed result: **CLARIFY**, targeted KK question, no backend execution. This probe is excluded from official metrics.

If console/report writing is interrupted after all model calls are saved, `python evaluation/recover_report.py evaluation/results/<run-id>` re-executes the original scorer without new inference. It checks source hashes, complete unique IDs and raw/prediction consistency first.

`evaluation/results/baseline.json` and `.md` hold the last measured baseline or an explicit blocked report when none exists. Each attempt has an immutable timestamp directory. `raw.jsonl` contains actual model responses, `predictions.json` contains post-policy IDs, `official_stdout.txt` is the untouched evaluator's output. Failed later attempts do not overwrite a measured baseline. Missing API credentials yield **not measured**, not zero accuracy or fake predictions.

Passed/Failed = primary-scenario correctness. Full-match = set equality. Multi-intent recall = matched expected intents / all expected intents on multi-intent examples. Additional diagnostics report extra intents, incorrect SYS outcomes, schema failures and confusion pairs. Average/p95 latency includes routing retries and errors, excludes policy and audio; p95 uses nearest rank. It is not voice end-to-end latency.

Transport integration tests use `httpx.MockTransport` only to verify request/repair/error handling. They do not establish model accuracy and are never used as baseline predictions. The large synthetic dataset has not been generated.

## Decisions and actual starter-kit differences

- Reference date is **2026-10-01**, not the OS date.
- `find_client` inputs include `phone|iin`; action parameters include backend IDs beyond the slots catalog. Validator does not falsely reject these.
- An OGPO victim can reference another client's policy. Foreign-key existence is checked, ownership equality is not imposed.
- System IDs are exact canonical names; OOD does not automatically hand off.
- Missing execution slots do not automatically prevent scenario routing.
- BUILD_SPEC treats confidence as diagnostic. README reference thresholds are not used to override evidence or trigger duplicate calls.
- B2 adds local evidence IDs, exact quote, topic relation and a clarification question to the conceptual contract for testable attribution and transitions. No canonical IDs are altered.
- Simple system/business results are exclusive. Mixed explicit segments requiring simultaneous system/business outcomes are not yet represented and must be added with tests if measured failures require them.

API contract references: [Responses structured output](https://developers.openai.com/api/docs/guides/structured-outputs), [gpt-6-astra](https://developers.openai.com/api/docs/models/gpt-6-astra).
