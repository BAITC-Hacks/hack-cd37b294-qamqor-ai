"""Profile saved real calls. Incomplete legacy timing/usage is explicitly unavailable."""
import argparse
from collections import defaultdict
import json
from math import ceil
from pathlib import Path
from statistics import mean, median, correlation
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.router.telemetry import usage_metrics, field_bytes


def distribution(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"n": 0, **dict.fromkeys(("mean", "median", "p50", "p75", "p90", "p95", "max"))}
    return {"n": len(values), "mean": mean(values), "median": median(values),
            **{f"p{p}": values[max(0, ceil(len(values) * p / 100) - 1)] for p in (50, 75, 90, 95)},
            "max": max(values)}


def profile(records):
    requests = []
    for record in records:
        for attempt in record.get("attempts", []):
            raw = attempt.get("raw_response") or {}
            output_parts = [c.get("text", "") for item in raw.get("output", []) if item.get("type") == "message"
                            for c in item.get("content", []) if c.get("type") == "output_text"]
            try:
                sizes = field_bytes(json.loads("".join(output_parts)))
            except (ValueError, TypeError, AttributeError):
                sizes = {}
            requests.append({"id": record["id"], "attempt": attempt["number"],
                "retry_count": attempt["number"] - 1, "turn_retry_count": len(record["attempts"]) - 1,
                "response_id": attempt.get("response_id"), "effort": attempt.get("effort"),
                "attempt_wall_ms": attempt.get("latency_ms"), "http_wall_ms": attempt.get("http_wall_ms"),
                "schema_validation_ms": attempt.get("schema_validation_ms"),
                "policy_latency_ms": attempt.get("policy_latency_ms"),
                "response_json_bytes": attempt.get("response_json_bytes"),
                "output_field_bytes": attempt.get("output_field_bytes", sizes),
                "schema_valid": attempt.get("schema_valid"),
                **usage_metrics(raw)})
    names = ["attempt_wall_ms", "http_wall_ms", "schema_validation_ms", "policy_latency_ms", "response_json_bytes",
             "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "total_tokens"]
    distributions = {name: distribution([r[name] for r in requests]) for name in names}
    distributions["router_wall_ms"] = distribution([r.get("latency_ms") for r in records])
    distributions["turn_policy_ms"] = distribution([r.get("policy_latency_ms") for r in records])
    eligible = [r for r in requests if r["input_tokens"] is not None and r["cached_tokens"] is not None]
    input_total = sum(r["input_tokens"] for r in eligible)
    fields = defaultdict(list)
    for request in requests:
        for key, size in request["output_field_bytes"].items():
            fields[key].append(size)
    pairs = [(r["output_tokens"], r["http_wall_ms"]) for r in requests
             if r["output_tokens"] is not None and r["http_wall_ms"] is not None and r["retry_count"] == 0]
    corr = None
    if len(pairs) > 2 and len({p[0] for p in pairs}) > 1 and len({p[1] for p in pairs}) > 1:
        corr = correlation([p[0] for p in pairs], [p[1] for p in pairs])
    return {"turns": len(records), "requests": len(requests), "distributions": distributions,
            "cache_hit_ratio": sum(r["cached_tokens"] for r in eligible) / input_total if input_total else None,
            "cache_hit_ratio_definition": "sum(cached_tokens) / sum(input_tokens), requests with both fields only",
            "cache_observed_requests": len(eligible), "requests_with_cache_hits": sum(r["cached_tokens"] > 0 for r in eligible),
            "retry_turns": sum(len(r.get("attempts", [])) > 1 for r in records),
            "retry_rate": sum(len(r.get("attempts", [])) > 1 for r in records) / len(records) if records else None,
            "schema_failed_attempts": sum(r["schema_valid"] is False for r in requests),
            "schema_failures": sum(r.get("error_kind") == "SCHEMA_ERROR" for r in records),
            "output_field_utf8_bytes": {key: distribution(values) for key, values in fields.items()},
            "initial_output_tokens_http_wall_correlation": corr,
            "measurement_limits": ["HTTP wall includes provider compute, queue, network and response download; no server phase breakdown",
                                   "Field sizes are bytes, not estimated tokens; usage output_tokens includes reasoning",
                                   "Missing fields are null, not zero; pXX uses nearest rank; median interpolates",
                                   "Retry attempts remain separate; policy only runs after the accepted final proposal"],
            "request_records": requests}


def write_profile(run_dir, output_dir=None):
    rows = [json.loads(line) for line in (run_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines()]
    report = {"source_run": str(run_dir.resolve()), **profile(rows)}
    target = output_dir or run_dir
    target.mkdir(parents=True, exist_ok=True)
    (target / "latency_profile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Observed latency profile", "", f"Source: `{run_dir}`", "",
             f"{report['turns']} turns; {report['requests']} real requests. No cached predictions.", "",
             "| Metric | n | Mean | Median | p50 | p75 | p90 | p95 | Max |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, dist in report["distributions"].items():
        lines.append("| " + name + " | " + " | ".join("unavailable" if dist[k] is None else f"{dist[k]:.3f}"
                     for k in ("n", "mean", "median", "p50", "p75", "p90", "p95", "max")) + " |")
    lines += ["", f"Cache token hit ratio: {report['cache_hit_ratio']}; requests with hits: {report['requests_with_cache_hits']}/{report['cache_observed_requests']}",
              f"Retry rate: {report['retry_rate']}; failed schema attempts: {report['schema_failed_attempts']}; final schema failures: {report['schema_failures']}",
              "", "\n".join(report["measurement_limits"])]
    (target / "latency_profile.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    r = write_profile(args.run_directory, args.output_dir)
    print(json.dumps({"turns": r["turns"], "requests": r["requests"], "cache_hit_ratio": r["cache_hit_ratio"]}))
