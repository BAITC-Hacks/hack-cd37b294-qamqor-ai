BUILD STATUS

Status: executed
Official examples: 104
Passed: 103
Failed: 1
Exact/full-match: 103 / 104 (0.9903846153846154)
Recall: 1.0 (hits 26 / 26)

Top confusion pairs: [{'expected': 'SC30', 'predicted': 'SYS_UNCLEAR', 'count': 1}]
Schema failures: 0
System-intent failures: 1

Average router latency: 5782.494069230429 ms
P95 router latency: 8922.875599993858 ms

Files changed: see README.md and BUILD_LOG.md; per-run code hashes in metadata.json
Tests executed: see tests.xml and BUILD_LOG.md; tests are not model accuracy
Known blockers: none
Next highest-impact fix: Review measured error categories before modifying routing
Passed/Failed refer to primary scenario correctness. Full-match uses set equality.
This baseline scores policy decisions, not raw proposals. No synthetic results are included.
