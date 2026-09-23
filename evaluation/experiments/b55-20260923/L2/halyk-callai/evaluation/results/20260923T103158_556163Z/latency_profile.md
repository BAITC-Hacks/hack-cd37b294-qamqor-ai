# Observed latency profile

Source: `C:\HackAlem\PHOENIX-PATCH-WEDGE-FORGE-v1\halyk-callai\evaluation\experiments\b55-20260923\L2\halyk-callai\evaluation\results\20260923T103158_556163Z`

104 turns; 105 real requests. No cached predictions.

| Metric | n | Mean | Median | p50 | p75 | p90 | p95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| attempt_wall_ms | 105.000 | 8445.005 | 8134.746 | 8134.746 | 9414.746 | 11132.371 | 12889.902 | 18149.638 |
| http_wall_ms | 105.000 | 8444.547 | 8134.359 | 8134.359 | 9414.333 | 11131.919 | 12889.357 | 18149.050 |
| provider_lifecycle_ms | 105.000 | 7838.095 | 8000.000 | 8000.000 | 9000.000 | 11000.000 | 12000.000 | 16000.000 |
| schema_validation_ms | 105.000 | 0.186 | 0.173 | 0.173 | 0.190 | 0.281 | 0.295 | 0.421 |
| policy_latency_ms | 104.000 | 0.034 | 0.031 | 0.031 | 0.035 | 0.040 | 0.044 | 0.169 |
| response_json_bytes | 105.000 | 20517.695 | 20271.000 | 20271.000 | 20913.000 | 22091.000 | 22936.000 | 24738.000 |
| input_tokens | 105.000 | 9539.962 | 9536.000 | 9536.000 | 9540.000 | 9542.000 | 9544.000 | 9859.000 |
| cached_tokens | 105.000 | 9440.000 | 9440.000 | 9440.000 | 9440.000 | 9440.000 | 9440.000 | 9440.000 |
| cache_write_tokens | 105.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| output_tokens | 105.000 | 335.695 | 323.000 | 323.000 | 382.000 | 471.000 | 575.000 | 759.000 |
| reasoning_tokens | 105.000 | 5.571 | 0.000 | 0.000 | 0.000 | 27.000 | 42.000 | 59.000 |
| total_tokens | 105.000 | 9875.657 | 9862.000 | 9862.000 | 9921.000 | 10020.000 | 10119.000 | 10314.000 |
| router_wall_ms | 104.000 | 8527.036 | 8297.036 | 8252.652 | 9441.731 | 11731.312 | 13345.940 | 18150.475 |
| turn_policy_ms | 104.000 | 0.034 | 0.031 | 0.031 | 0.035 | 0.040 | 0.044 | 0.169 |

Cache token hit ratio: 0.9895217710762547; requests with hits: 105/105
Retry rate: 0.009615384615384616; failed schema attempts: 1; final schema failures: 0

HTTP wall includes provider compute, queue, network and response download; no server phase breakdown
Provider lifecycle uses returned created_at/completed_at with one-second quantization; not a decoding-only timer
Field sizes are bytes, not estimated tokens; usage output_tokens includes reasoning
Missing fields are null, not zero; pXX uses nearest rank; median interpolates
Retry attempts remain separate; policy only runs after the accepted final proposal
