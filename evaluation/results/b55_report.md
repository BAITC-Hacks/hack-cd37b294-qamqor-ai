# B5.5 LATENCY REPORT

Batch: b55-20260923. All variants complete: False.

| Variant | Correctness gate | Primary | Full | Recall | Mean ms | Median ms | P95 ms | Max ms | Retries | Tests |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| L0 | PASS | 104 | 104 | 26/26 | 8830.40 | 8552.00 | 12144.58 | 20207.26 | 1 | 76 |
| L1 | FAIL | 102 | 102 | 26/26 | not ranked | not ranked | not ranked | not ranked | 1 | 80 |
| L2 | PASS | 104 | 104 | 26/26 | 8527.04 | 8297.04 | 13345.94 | 18150.47 | 1 | 83 |
| L3 | PENDING | - | - | -/26 | not ranked | not ranked | not ranked | not ranked | - | - |
| L4 | PENDING | - | - | -/26 | not ranked | not ranked | not ranked | not ranked | - | - |

Latency of failed correctness variants is retained as raw diagnostic data in JSON, not ranked as an improvement.

Historical B5 before: {"n": 104, "mean": 9347.581914425693, "median": 8848.54555001948, "p50": 8820.535000006203, "p75": 10618.479299999308, "p90": 12766.570499981754, "p95": 13230.123899993487, "max": 16864.67070004437}

Selected variant: L2

Selected after: {"n": 104, "mean": 8527.035731728784, "median": 8297.036350006238, "p50": 8252.652199997101, "p75": 9441.731499973685, "p90": 11731.312299962156, "p95": 13345.940300030634, "max": 18150.474799971562}

Improvement fractions: {"mean": 0.08778165200463217, "p95": -0.008753992095055452}

LATENCY BLOCKER REMAINS

Each variant uses a fresh complete set of responses; no prediction reuse. Fixed model/effort, concurrency 2. Sequential runs include provider/network variability. Development set reuse does not measure hidden-test generalization.
