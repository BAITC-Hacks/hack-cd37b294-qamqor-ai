from evaluation.b55_report import correctness_gate, select_variant


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


def test_selection_rejects_fast_incorrect_and_prefers_both_latency_targets():
    def candidate(name, gate, mean, p95):
        return {"variant": name, "correctness_gate": gate, "profile": {"distributions": {"router_wall_ms": {"mean": mean, "p95": p95}}}}
    assert select_variant([candidate("L2", False, 1000, 2000)]) is None
    variants = [candidate("L2", True, 3000, 9000), candidate("L3", False, 2000, 3000), candidate("L4", True, 4000, 7000)]
    assert select_variant(variants)["variant"] == "L4"
