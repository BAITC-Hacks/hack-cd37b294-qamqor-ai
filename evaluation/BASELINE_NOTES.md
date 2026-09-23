# Official dev baseline — executed runs

These are measurements on the official **development** set, not hidden-test accuracy. Original inputs and evaluate.py remain unchanged. No synthetic examples are included. Each full inference run uses gpt-6-astra, low effort initially, at most one shared-budget medium retry, concurrency 2, provider-default temperature, all 40+3 catalog entries.

## Initial run: 20260923T094057_604544Z

- 104 real inference records; primary 100/104 (96.15%); full-match 99/104 (95.19%); multi-intent recall 23/26 (88.46%).
- RU primary/full: 49/52; KK: 44/45; mixed primary: 7/7, full: 6/7.
- Unrecovered schema failures: 0. Schema-repair calls: 12. API failures: 0.
- System-intent failures: 2 unnecessary SYS_UNCLEAR results.
- Mean router wall time: 8713.43 ms; nearest-rank p95: 17380.87 ms. Includes retries, excludes audio and policy.
- Scorer completed but initial console output failed on Kazakh characters in Windows cp1251. Saved raw calls/predictions were recovered without new model requests; original scorer was executed again. The inference run's metadata and hashes were preserved.

Five full-match failures were recorded: U039/U040 (inspection request unnecessarily clarified), U083 (secondary inspection task dropped), U085/U089 (document delivery task dropped while a second task remained). Four have the wrong primary scenario; U083 retains the right primary but misses a secondary task.

## Corrections based on these failures

1. Separate routing to requested work from checking execution preconditions. Canonical SC20 examples request inspection without declaring a claim number; the negative exception requires evidence that no claim exists. The router must not invent registration, but missing registration data alone must not erase an explicit inspection task. The same general rule preserves explicit dependent tasks in multi-intent turns.
2. Distinguish document-delivery work from ambiguous charged-payment/issuance problems. The latter still requires evidence or clarification, as BUILD_SPEC requires. No new keyword rules or test-ID mapping were added.
3. Normalize reversed boundary comparisons only when a real catalog rule exactly matches the pair and its opposite endpoint is a proposed candidate. Canonical rule direction, supporting evidence, status and scenario choice remain unchanged. Missing/conflicting boundaries continue to clarify. Raw model response and normalization metadata remain in the trace.
4. Configure console UTF-8; add complete-run report recovery with source-hash, ID coverage and raw/prediction consistency checks.
5. Add a local .gitignore because halyk-callai became its own Git root; .env and the venv are excluded.

Regression suite after these changes: **76 passed**. The follow-up full run is recorded independently; compare both complete runs, not a mixture of cached answers and new predictions. Improvements on this reused dev set are not an independent generalization estimate.

## Follow-up run: 20260923T095132_960641Z

- All 104 real inference records completed; original evaluate.py exited 0.
- Primary **104/104 (100%)**, full-match **104/104 (100%)**, multi-intent recall **26/26 (100%)**.
- RU **52/52**, KK **45/45**, mixed **7/7**, each for primary and full-match.
- All five previous full-match failures are corrected; no new failures on this run.
- Final schema failures **0**, API failures **0**, system-intent failures **0**. One schema-repair retry (U099, boundary without a candidate); one validated boundary orientation normalization. The recovered retry is counted, not hidden.
- Mean router wall time **9347.58 ms**, nearest-rank p95 **13230.12 ms**. The mean increased from 8713.43 ms even though p95 and repair count decreased. Two live runs do not establish a stable latency distribution.
- Raw outputs, predictions, code/source/prompt hashes and official output are retained separately for both runs.

## Separate BUILD_SPEC boundary guard

Executed `python evaluation/run_boundary_probe.py` after the full run, with the same router. Result stored under `results/boundary_probe_20260923T100006_843729Z/`.

Input: “Ақша списали, бірақ полис келмеді”. Actual decision: **CLARIFY**, SYS_UNCLEAR, execution_allowed=false; targeted KK question asks whether issuance was confirmed or money was merely charged. The prompt correction therefore preserved this required ambiguity in the executed probe. This is one regression example, not an official accuracy metric or a broad safety guarantee.

## Next measured priority

No official routing errors remain in the latest run. The next performance issue is router latency (9.35 s average, 13.23 s p95) and the remaining unnecessary schema-repair call. Profile request/output token usage and test compact output instructions while preserving the full catalog, fixed model and evidence contract; measure against the same immutable scorer. B6+ product capabilities remain unimplemented.
