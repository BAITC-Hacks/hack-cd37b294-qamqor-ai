# Observed latency profile

Source: `C:\HackAlem\PHOENIX-PATCH-WEDGE-FORGE-v1\halyk-callai\evaluation\experiments\b55-20260923\L1\halyk-callai\evaluation\results\20260923T101514_156514Z`

104 turns; 105 real requests. No cached predictions.

| Metric | n | Mean | Median | p50 | p75 | p90 | p95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| attempt_wall_ms | 105.000 | 18693.650 | 8253.159 | 8253.159 | 9534.962 | 11311.396 | 12254.771 | 552436.970 |
| http_wall_ms | 105.000 | 18693.010 | 8252.736 | 8252.736 | 9534.532 | 11310.799 | 12254.027 | 552436.966 |
| schema_validation_ms | 103.000 | 0.379 | 0.180 | 0.180 | 0.244 | 0.334 | 0.390 | 17.775 |
| policy_latency_ms | 102.000 | 0.036 | 0.032 | 0.032 | 0.039 | 0.049 | 0.054 | 0.162 |
| response_json_bytes | 103.000 | 20293.748 | 20183.000 | 20183.000 | 20684.000 | 21421.000 | 21949.000 | 24664.000 |
| input_tokens | 103.000 | 9539.350 | 9536.000 | 9536.000 | 9540.000 | 9542.000 | 9544.000 | 9787.000 |
| cached_tokens | 103.000 | 9533.010 | 9533.000 | 9533.000 | 9537.000 | 9539.000 | 9541.000 | 9552.000 |
| cache_write_tokens | 103.000 | 3.340 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 344.000 |
| output_tokens | 103.000 | 346.835 | 348.000 | 348.000 | 404.000 | 469.000 | 523.000 | 761.000 |
| reasoning_tokens | 103.000 | 2.311 | 0.000 | 0.000 | 0.000 | 0.000 | 26.000 | 51.000 |
| total_tokens | 103.000 | 9886.184 | 9884.000 | 9884.000 | 9946.000 | 10004.000 | 10062.000 | 10316.000 |
| router_wall_ms | 104.000 | 18874.740 | 8287.210 | 8282.682 | 9537.870 | 11312.418 | 12256.041 | 552438.265 |
| turn_policy_ms | 102.000 | 0.036 | 0.032 | 0.032 | 0.039 | 0.049 | 0.054 | 0.162 |

Cache token hit ratio: 0.9993354048076796; requests with hits: 103/103
Retry rate: 0.009615384615384616; failed schema attempts: 1; final schema failures: 0

HTTP wall includes provider compute, queue, network and response download; no server phase breakdown
Field sizes are bytes, not estimated tokens; usage output_tokens includes reasoning
Missing fields are null, not zero; pXX uses nearest rank; median interpolates
Retry attempts remain separate; policy only runs after the accepted final proposal
