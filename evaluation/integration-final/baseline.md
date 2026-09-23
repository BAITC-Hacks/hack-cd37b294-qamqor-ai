BUILD STATUS

Status: executed
Official examples: 104
Passed: 100
Failed: 4
Exact/full-match: 99 / 104 (0.9519230769230769)
Recall: 0.8846153846153846 (hits 23 / 26)

Top confusion pairs: [{'expected': 'SC22', 'predicted': 'SYS_UNCLEAR', 'count': 2}, {'expected': 'SC20', 'predicted': 'SYS_UNCLEAR', 'count': 1}, {'expected': 'SC19', 'predicted': 'SYS_UNCLEAR', 'count': 1}]
Schema failures: 0
System-intent failures: 4

Average router latency: 4751.964580772507 ms
P95 router latency: 8601.24770004768 ms

Files changed: see README.md and BUILD_LOG.md; per-run code hashes in metadata.json
Tests executed: see tests.xml and BUILD_LOG.md; tests are not model accuracy
Known blockers: none
Next highest-impact fix: Review measured error categories before modifying routing
Passed/Failed refer to primary scenario correctness. Full-match uses set equality.
This baseline scores policy decisions, not raw proposals. No synthetic results are included.
