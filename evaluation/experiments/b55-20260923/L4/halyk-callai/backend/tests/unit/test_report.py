from evaluation.report import summarize, percentile95


def test_metrics_distinguish_primary_set_match_and_recall():
    # Unit fixtures only, not a model run or a claimed official result.
    gold = [
        {"id": "test1", "text": "test", "expected": ["SC01", "SC02"], "type": "multi_intent", "lang": "ru"},
        {"id": "test2", "text": "test", "expected": ["SYS_UNCLEAR"], "type": "unclear", "lang": "kk"},
        {"id": "test3", "text": "test", "expected": ["SC33"], "type": "single", "lang": "mixed"},
    ]
    records = [
        {"id": "test1", "prediction": ["SC02", "SC01"], "attempts": [{"schema_valid": True}], "latency_ms": 10},
        {"id": "test2", "prediction": ["SC33"], "attempts": [{"schema_valid": True}], "latency_ms": 20},
        {"id": "test3", "prediction": [], "error_kind": "SCHEMA_ERROR", "attempts": [{"schema_valid": False}], "latency_ms": 30},
    ]
    result = summarize(gold, records)
    assert result["passed"] == 0 and result["full_match_count"] == 1
    assert result["recall"] == 1 and result["recall_total"] == 2
    assert result["system_intent_failures"] == 1 and result["schema_failures"] == 1
    assert result["average_router_latency_ms"] == 20 and result["p95_router_latency_ms"] == 30


def test_nearest_rank_latency():
    assert percentile95(list(range(1, 101))) == 95
    assert percentile95([]) is None
