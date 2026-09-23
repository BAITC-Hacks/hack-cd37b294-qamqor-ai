# Observed latency profile

Source: `C:\HackAlem\PHOENIX-PATCH-WEDGE-FORGE-v1\halyk-callai\evaluation\experiments\b55-20260923\L0\halyk-callai\evaluation\results\20260923T100713_410096Z`

104 turns; 105 real requests. No cached predictions.

| Metric | n | Mean | Median | p50 | p75 | p90 | p95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| attempt_wall_ms | 105.000 | 8745.782 | 8508.854 | 8508.854 | 10001.150 | 11471.468 | 12143.959 | 20206.767 |
| http_wall_ms | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| provider_lifecycle_ms | 105.000 | 8133.333 | 8000.000 | 8000.000 | 9000.000 | 11000.000 | 12000.000 | 16000.000 |
| schema_validation_ms | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| policy_latency_ms | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| response_json_bytes | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| input_tokens | 105.000 | 9539.229 | 9536.000 | 9536.000 | 9540.000 | 9542.000 | 9544.000 | 9782.000 |
| cached_tokens | 105.000 | 9533.000 | 9533.000 | 9533.000 | 9537.000 | 9539.000 | 9541.000 | 9552.000 |
| cache_write_tokens | 105.000 | 3.229 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 339.000 |
| output_tokens | 105.000 | 348.905 | 337.000 | 337.000 | 390.000 | 490.000 | 568.000 | 768.000 |
| reasoning_tokens | 105.000 | 2.762 | 0.000 | 0.000 | 0.000 | 0.000 | 25.000 | 79.000 |
| total_tokens | 105.000 | 9888.133 | 9876.000 | 9876.000 | 9931.000 | 10030.000 | 10113.000 | 10323.000 |
| router_wall_ms | 104.000 | 8830.401 | 8552.001 | 8549.817 | 10008.278 | 11496.198 | 12144.579 | 20207.260 |
| turn_policy_ms | 104.000 | 0.061 | 0.058 | 0.058 | 0.066 | 0.076 | 0.081 | 0.098 |

Cache token hit ratio: 0.9993470571145315; requests with hits: 105/105
Retry rate: 0.009615384615384616; failed schema attempts: 1; final schema failures: 0

HTTP wall includes provider compute, queue, network and response download; no server phase breakdown
Provider lifecycle uses returned created_at/completed_at with one-second quantization; not a decoding-only timer
Field sizes are bytes, not estimated tokens; usage output_tokens includes reasoning
Missing fields are null, not zero; pXX uses nearest rank; median interpolates
Retry attempts remain separate; policy only runs after the accepted final proposal
