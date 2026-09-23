from evaluation.b55_report import correctness_gate


def test_latency_candidate_requires_all_correctness_gates():
    metrics = dict(total=104, attempted=104, passed=104, full_match_count=104,
                   recall_hit=26, recall_total=26, schema_failures=0, api_failures=0, system_intent_failures=0)
    boundary = dict(passed=True, decision=dict(action="CLARIFY", execution_allowed=False))
    execution = dict(snapshot_unchanged=True, steps=dict(tests=0, official=0, boundary=0))
    assert correctness_gate(metrics, boundary, execution)
    assert not correctness_gate({**metrics, "full_match_count": 103}, boundary, execution)
    assert not correctness_gate({**metrics, "api_failures": 1}, boundary, execution)
    assert not correctness_gate(metrics, {**boundary, "passed": False}, execution)
    assert not correctness_gate(metrics, boundary, {**execution, "snapshot_unchanged": False})
