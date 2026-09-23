from app.router.telemetry import usage_metrics
from evaluation.latency_profile import distribution, profile


def test_usage_does_not_invent_zero_for_absent_fields():
    assert all(v is None for v in usage_metrics({}).values())
    assert usage_metrics({"usage": {"input_tokens_details": {"cached_tokens": 0}}})["cached_tokens"] == 0


def test_profile_counts_retries_and_uses_weighted_cache_ratio():
    def attempt(number, inputs, cached):
        return {"number": number, "latency_ms": 100, "schema_valid": number == 2,
                "raw_response": {"usage": {"input_tokens": inputs, "input_tokens_details": {"cached_tokens": cached}}}}
    rows = [{"id": "fixture", "latency_ms": 201, "attempts": [attempt(1, 100, 50), attempt(2, 300, 300)]}]
    result = profile(rows)
    assert result["requests"] == 2 and result["retry_rate"] == 1
    assert result["cache_hit_ratio"] == 350 / 400
    assert result["schema_failed_attempts"] == 1
    assert result["distributions"]["response_json_bytes"]["n"] == 0
    assert result["request_records"][0]["policy_latency_ms"] is None


def test_distribution_nearest_rank_and_missing_samples():
    d = distribution([None, 1, 2, 3, 4])
    assert d == {"n": 4, "mean": 2.5, "median": 2.5, "p50": 2, "p75": 3, "p90": 4, "p95": 4, "max": 4}
    assert distribution([])["mean"] is None
