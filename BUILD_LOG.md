# Executed build record

## Scope and inputs

AGENTS.md and BUILD_SPEC.md were read completely before edits. The repository had methodology documents and the official starter kit, no existing backend to replace. B0–B5 follows the locked specification. User first requested the offline build, then supplied local API credentials. Real inference and official evaluation have now completed.

Official source files remain byte-identical to the SHA-256 inventory. No gold labels, evaluator logic, catalog semantics or original sample dialogs were edited. No large synthetic dataset was generated.

## Executed milestones

| Milestone | Actual execution |
|---|---|
| B0 | `python scripts/validate_dataset.py --output evaluation/results/dataset_validation.json`: valid; 40+3 IDs, 43 slots, 31 actions, 104 official examples, 10 dialogs. D01 length warning only. 9 initial tests passed |
| B1 | `python -m app.catalog.compiler`: all 40 scenarios, 3 system intents, 63 directional rules; 31,109 compact characters. 3 tests passed |
| B2 | Strict contracts and provenance validation: 20 tests passed |
| B3 | Responses adapter, structured schema, bounded repair/reanalysis, error isolation: 11 initial transport tests passed. Subsequently two real full runs (208 official turns total) and one BUILD_SPEC boundary probe executed |
| B4 | Policy transitions and urgency: 16 initial tests passed; additional pending-action regression passed |
| B5 | Two complete real 104-record runs. Initial primary 100/104, full-match 99/104, recall 23/26. After measured fixes: primary and full-match 104/104, recall 26/26; original evaluate.py exited 0. Latest mean latency 9347.58 ms, p95 13230.12 ms |

## Packaging and verification

- Created local Python 3.12.10 venv, successfully installed `.[test]` and pinned resolved dependencies in requirements.lock.
- Latest complete run: **76 tests passed**, zero failed. JUnit evidence: `evaluation/results/tests.xml`.
- `python -m pip check`: no broken requirements.
- `python -m compileall -q backend/app evaluation scripts`: passed again after the boundary probe script was added.
- `docker compose config --quiet`: passed. Docker image build/container execution has NOT run.
- Initial `scripts/run.ps1` startup passed health; readiness was 503 before credentials. After credentials and B5, uvicorn was started again: real HTTP health passed, readiness 200. A live `POST /api/route` with a goodbye turn returned END / SYS_GOODBYE through the real LLM. Saved in `evaluation/results/live_http_route_smoke.json`. The temporary server was stopped after verification. No voice or business-action execution is claimed.
- Official-file hashes rechecked against the pre-existing starter_kit_inventory.json: unchanged.

## Fixes made during validation

- Switched API tests to ASGITransport with explicit lifespan after the freshly installed Starlette version warned about deprecated TestClient/httpx usage; no extra framework added.
- Policy cannot mark a task complete while a backend action is pending. Regression verifies no premature RESTORE.
- Malformed dataset rows produce a validation report rather than an AttributeError traceback.
- Evaluation preserves an existing measured baseline when a later preflight fails; with no measured baseline, latest blocked status is saved. Missing credentials do not become false 0% accuracy.
- UTF-8 console output fixes Kazakh text failures in Windows cp1251. First full run was recovered from saved real responses by executing the untouched scorer again, without new model calls. Recovery verifies source hashes and record/prediction consistency.
- Prompt separates explicitly requested tasks from unknown execution preconditions. All five initial full-match failures were corrected in the second full run. Charged-payment/unknown-issuance ambiguity still produces CLARIFY in the live BUILD_SPEC probe.
- Reversed boundary endpoints are normalized only when the cited canonical rule exactly matches the pair and one endpoint is a candidate. Evidence/status/rule direction are preserved; five regression tests cover allowed and rejected cases. Raw outputs and normalizations remain traceable.
- A nested Git repository appeared at halyk-callai; local .gitignore now excludes .env, venv and raw responses independently of the parent repository.

## Changed files

Root: `.gitignore`, `README.md`.

New implementation under `halyk-callai/`:

```text
.env.example                  local .env is ignored; key supplied locally
.gitignore
pyproject.toml                requirements.lock
Dockerfile                    docker-compose.yml
Makefile                      README.md
BUILD_LOG.md
backend/app/
  __init__.py                 main.py
  catalog/                    loader.py, compiler.py, boundaries.py, __init__.py
  config/                     settings.py, __init__.py
  router/                     schemas.py, validator.py, prompt.py, llm.py, __init__.py
  policy/                     engine.py, rules.py, decisions.py, __init__.py
backend/tests/
  conftest.py
  unit/                       test_dataset.py, test_compiler.py, test_contracts.py,
                              test_policy.py, test_report.py
  integration/                test_llm_transport.py, test_api.py, test_eval_preflight.py
data/compiled_catalog.json
evaluation/                   __init__.py, run_official.py, report.py,
                              recover_report.py, run_boundary_probe.py, BASELINE_NOTES.md
evaluation/results/           validation, JUnit, preflight history, two full live runs,
                              BUILD_SPEC boundary probe and latest baseline reports
scripts/                      validate_dataset.py, smoke_test.py, run.ps1
```

## Current measured result and next step

B0–B5 is **executed**. Latest official run: `20260923T095132_960641Z`, 104/104 primary and full-match, 26/26 multi-intent recall, no final schema/API/system-intent errors. One schema repair succeeded. Details and first-run comparison: `evaluation/BASELINE_NOTES.md`. These are reused development-set results, not hidden-test accuracy. Run `.\scripts\run.ps1 baseline` to make a fresh complete inference run.

Next measured issue: router latency (mean 9.35 s, p95 13.23 s) and remaining unnecessary repair. Investigate token usage and evaluate compact output instructions without dropping catalog entries or evidence. B6+ (persistent conversation service, complete session/chat API, action executor, KB answers, supervisor UI and voice) remains unimplemented; no product-level or voice completion is claimed.

## 2026-09-23 — frozen L2 product integration B6–B14

User stopped L3/L4 optimization. Preserved exact L2 under golden/L2, including historical 104/104 scorer output, raw requests and manifests; restored 16 protected source files. Their SHA256 hashes remain identical. L4 was stopped and marked incomplete; no score is inferred from partial output.

Implemented and integrated SQLite sessions and operation ledger, topic state, scoped canonical slots and corrections, all 31 mock backend actions, explicit version-bound confirmation, KB lookup, RU/KK responses, asynchronous SQLite/JSONL traces, customer and supervisor Next.js pages, six live demo shortcuts, final-utterance voice adapters and one-command Windows startup.

Measured defect and fix: ignored local .env had CALLAI_MODEL=gpt-6-luna. First integration evaluation (20260923T111356_273394Z) was therefore NOT golden L2: full-match 99/104, recall 23/26. Preserved it and the failed live correction/restore traces. Restored CALLAI_MODEL=gpt-6-astra as explicitly required by golden configuration; did not modify router prompt, policy, boundary rules or output schema. Added startup rejection of a mismatched runtime model.

Real final official regression: evaluation/integration-final-astra/20260923T111919_964539Z. Primary 104/104, full-match 104/104, recall 26/26. Mean 8254.112 ms, P95 13129.871 ms. Zero final schema/API/system-intent failures; one successful schema repair. Original official scorer executed unchanged. Boundary probe 20260923T112357_236619Z: PASS, CLARIFY, execution_allowed=false.

Real product acceptance: six paths pass, 12 actual L2 turns, mean total text latency 7899.272 ms. Includes canonical office response, ambiguous payment followed by actual backend lookup, corrected email/evidence, stale confirmation rejection, actual confirmation, exact replay, SWITCH/RESTORE, Kazakh response and missing-slot collection. Final guard fixes retain unresolved secondary intents and record backend failures; covered by integration regressions.

Voice probe: real OpenAI audio requests and real app endpoints, generated audio fixtures. RU 11029.266 ms and KK 9794.209 ms end-to-end processing. Initial Kazakh autodetection produced Latin-script noise; supplying the explicit UI RU/KK hint corrected script/language in the rerun. Output MP3 and transcripts retained under evaluation/voice-probe. Not a human microphone/speaker or broad speech accuracy test. Pipecat optional bridge is unexecuted; actual working transport is browser MediaRecorder -> final STT -> common chat -> TTS.

Browser found a React cleanup exception from implicitly returning scrollIntoView; changed the effect to return nothing explicitly. Actual browser rerun completed a real boundary query and showed the real supervisor evidence. Fixed page-level scrolling and checked desktop and 390x844 mobile layout; mobile document matched viewport with composer visible. Screenshots: docs/supervisor.png, docs/customer.png, docs/customer-mobile.png.

Executed validation: 131 pytest PASS (evaluation/product-tests.xml), one Node playback interruption test PASS, full dataset validator PASS with only original D01 warning, compileall PASS, pip check PASS, Next.js production build PASS, HTTP health/readiness/frontend smoke PASS, .\scripts\run.ps1 demo actually started both servers. Runtime /ready verifies model gpt-6-astra. Current golden hash verification: 16/16 match.

Limits: all business execution is mock; outbox records are not real delivery. Calendar slots are a documented simulation because starter kit has no availability calendar. No production authentication or identity proofing; bind only loopback. Human-microphone and noisy/multi-speaker Kazakh tests remain unverified. No synthetic training corpus generated. No routing latency experiment added.
