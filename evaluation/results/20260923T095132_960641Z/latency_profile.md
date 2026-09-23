# Observed latency profile

Source: `C:\HackAlem\PHOENIX-PATCH-WEDGE-FORGE-v1\halyk-callai\evaluation\results\20260923T095132_960641Z`

104 turns; 105 real requests. No cached predictions.

| Metric | n | Mean | Median | p50 | p75 | p90 | p95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| attempt_wall_ms | 105.000 | 9258.041 | 8810.036 | 8810.036 | 10526.023 | 12761.161 | 13088.666 | 16864.144 |
| http_wall_ms | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| provider_lifecycle_ms | 105.000 | 8628.571 | 8000.000 | 8000.000 | 10000.000 | 12000.000 | 13000.000 | 16000.000 |
| schema_validation_ms | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| policy_latency_ms | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| response_json_bytes | 0.000 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| input_tokens | 105.000 | 9540.000 | 9536.000 | 9536.000 | 9540.000 | 9542.000 | 9544.000 | 9863.000 |
| cached_tokens | 105.000 | 9260.190 | 9440.000 | 9440.000 | 9440.000 | 9440.000 | 9440.000 | 9440.000 |
| cache_write_tokens | 105.000 | 276.810 | 93.000 | 93.000 | 97.000 | 99.000 | 102.000 | 9860.000 |
| output_tokens | 105.000 | 359.438 | 348.000 | 348.000 | 414.000 | 490.000 | 561.000 | 756.000 |
| reasoning_tokens | 105.000 | 2.514 | 0.000 | 0.000 | 0.000 | 0.000 | 20.000 | 71.000 |
| total_tokens | 105.000 | 9899.438 | 9891.000 | 9891.000 | 9955.000 | 10051.000 | 10111.000 | 10311.000 |
| router_wall_ms | 104.000 | 9347.582 | 8848.546 | 8820.535 | 10618.479 | 12766.570 | 13230.124 | 16864.671 |
| turn_policy_ms | 104.000 | 0.065 | 0.059 | 0.059 | 0.067 | 0.087 | 0.094 | 0.177 |

Cache token hit ratio: 0.9706698612358989; requests with hits: 103/105
Retry rate: 0.009615384615384616; failed schema attempts: 1; final schema failures: 0

HTTP wall includes provider compute, queue, network and response download; no server phase breakdown
Provider lifecycle uses returned created_at/completed_at with one-second quantization; not a decoding-only timer
Field sizes are bytes, not estimated tokens; usage output_tokens includes reasoning
Missing fields are null, not zero; pXX uses nearest rank; median interpolates
Retry attempts remain separate; policy only runs after the accepted final proposal
