# B5.5 prompt cache audit

## Baseline request, before semantic changes

The exact JSON sent by L1 is saved in each attempt's `request_payload`; its canonical SHA-256 is `request_sha256`. HTTP headers/credentials are never saved. L0 and L1 use byte-identical prompt.py, schemas.py, validator.py, compiler.py and policy files. Instrumentation copies the payload before retries append messages.

Invariant per normal request:

- Model gpt-6-astra; reasoning low; strict structured output contract in text.format.
- System message: routing instructions followed by one full compact canonical catalog.
- Catalog contains 40 scenarios, 3 system intents, all 63 directional rules, slot definitions and not-offered products. No gold examples or development utterances.
- The schema, its canonical enums, and prompt are deterministic.

Variable suffix: a single user message serializes RouterInput. Initially the latest user turn is the first property, followed by history, active scenario, topic stack, slots, evidence, pending action, backend and KB records, and response language. No variable state appears before the system catalog.

The client-visible ordering is known exactly; the provider's hidden rendered context is not exposed. text.format is supplied through the API, not duplicated into prompt text. Request-level medium effort on the bounded retry changes provider-side instructions and can prevent reuse of the low-effort prefix. The retry budget and efforts remain unchanged in this experiment.

## Observed baseline usage

The retained B5 run has 105 requests for 104 turns. Mean input 9540 tokens, cached input 9260.19, cache writes 276.81, output 359.44, reasoning 2.51. Weighted token cache-hit ratio: 97.067%. Caching is already verified from returned usage, not inferred from configuration.

Exact response JSON length and isolated schema-validation time were not recorded in B5. L1 adds these measurements; no missing historical field is backfilled with an estimate. Output field sizes are profiled as exact UTF-8 bytes. They are not advertised as tokenizer counts.

## Current official API support

[OpenAI prompt caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching), retrieved 2026-09-23, documents GPT-5.6 and later controls: prompt_cache_options mode, ttl=30m, explicit input_text breakpoints, and prewarm=true without output generation. [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) is kept fixed.

L2 will test an explicit breakpoint after the invariant instructions/catalog, state before the latest turn, and a separate prewarm call containing only that invariant prefix and the identical strict output schema. No catalog content is duplicated or removed. TTL is 30m. No new cache key is needed for cache routing on this model. Low and medium requests remain distinct configurations.

L0/L1 intentionally preserve the original request exactly. Successive runs can therefore reuse more than the invariant prefix: the provider may still have the entire earlier identical development input cached. No prediction is cached or reused by this application. Returned cached_tokens counts are real, but these runs cannot establish a cold-cache causal comparison. No cache-key change is hidden inside the instrumentation-only variant. L2's explicit breakpoint restricts writes to the invariant prefix; all prewarm calls and their usage are separately retained.

Prewarm must return no output; it is never parsed as a prediction or scored. Its time, usage and raw response are retained separately and excluded from per-turn router statistics. Only returned cached_tokens/cache_write_tokens establish actual reuse. API incompatibility must be reported, not silently disguised as a cache hit.

## Remaining schema repair: structural cause

The earlier failed output selected a system intent, left scenarios and alternatives empty, but emitted a business boundary check. The cited rule was real; its scenario_id was absent from both candidate lists. This violates the existing contract that a boundary must evaluate a candidate. L4 will reinforce candidate membership generally and require an empty boundary list when no business candidates exist. Invalid outputs will still be rejected. No ID-specific or utterance-specific runtime branch will be added.
