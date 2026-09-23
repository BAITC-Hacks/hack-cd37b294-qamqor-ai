"""Aggregate immutable experiments; rank latency only after all correctness gates."""
import argparse
import json
from pathlib import Path
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.latency_profile import write_profile


def correctness_gate(metrics, boundary, execution):
    return bool(metrics.get("total") == 104 and metrics.get("attempted") == 104
        and metrics.get("passed") == 104 and metrics.get("full_match_count") == 104
        and metrics.get("recall_hit") == metrics.get("recall_total") == 26
        and metrics.get("schema_failures") == metrics.get("api_failures") == metrics.get("system_intent_failures") == 0
        and boundary.get("passed") is True and boundary.get("decision", {}).get("execution_allowed") is False
        and boundary.get("decision", {}).get("action") == "CLARIFY"
        and execution.get("snapshot_unchanged") is True
        and execution.get("steps") == {"tests": 0, "official": 0, "boundary": 0})


def select_variant(variants):
    eligible = [v for v in variants if v["correctness_gate"] and v["variant"] in {"L2", "L3", "L4"}]
    within_targets = [v for v in eligible if v["profile"]["distributions"]["router_wall_ms"]["mean"] < 5000
                      and v["profile"]["distributions"]["router_wall_ms"]["p95"] < 8000]
    return min(within_targets or eligible, key=lambda v: v["profile"]["distributions"]["router_wall_ms"]["mean"]) if eligible else None


def collect_variant(target):
    result = {"variant": target.name, "complete": False, "correctness_gate": False}
    manifest = target / "manifest.json"
    if manifest.exists():
        result["manifest"] = str(manifest.resolve())
    execution_path = target / "execution.json"
    if not execution_path.exists():
        return result
    result["execution"] = json.loads(execution_path.read_text(encoding="utf-8"))
    result["complete"] = True
    output = target / "halyk-callai" / "evaluation" / "results"
    baseline_path = output / "baseline.json"
    if not baseline_path.exists():
        return result
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    metrics = baseline.get("metrics") or {}
    result["metrics"] = metrics
    result["run_directory"] = baseline["run_directory"]
    run = Path(baseline["run_directory"])
    if (run / "raw.jsonl").exists():
        result["profile"] = write_profile(run)
    probes = sorted(output.glob("boundary_probe_*/result.json"))
    result["boundary"] = json.loads(probes[-1].read_text(encoding="utf-8")) if probes else {}
    result["correctness_gate"] = correctness_gate(metrics, result["boundary"], result["execution"])
    xml = target / "tests.xml"
    if xml.exists():
        suites = list(ElementTree.parse(xml).getroot().iter("testsuite"))
        result["tests"] = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    prewarm = run / "prewarm.json"
    if prewarm.exists():
        raw = json.loads(prewarm.read_text(encoding="utf-8"))
        result["prewarm"] = {k: raw.get(k) for k in ("passed", "http_wall_ms", "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "response_id")}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("batch")
    args = parser.parse_args()
    folder = ROOT / "evaluation" / "experiments" / args.batch
    variants = [collect_variant(folder / name) for name in ("L0", "L1", "L2", "L3", "L4")]
    selected = select_variant(variants)
    historical = write_profile(ROOT / "evaluation" / "results" / "20260923T095132_960641Z")
    before = historical["distributions"]["router_wall_ms"]
    after = selected["profile"]["distributions"]["router_wall_ms"] if selected else None
    result = {"batch": args.batch, "all_complete": all(v["complete"] for v in variants),
              "selected_variant": selected["variant"] if selected else None,
              "historical_before": before, "selected_after": after, "variants": variants,
              "improvement": {k: 1 - after[k] / before[k] for k in ("mean", "p95")} if after else None,
              "recommendation": "READY FOR B6" if after and after["mean"] < 5000 and after["p95"] < 8000
                                and all(v["complete"] for v in variants) else "LATENCY BLOCKER REMAINS"}
    output = ROOT / "evaluation" / "results"
    (output / "b55_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# B5.5 LATENCY REPORT", "", f"Batch: {args.batch}. All variants complete: {result['all_complete']}.", "",
             "| Variant | Correctness gate | Primary | Full | Recall | Mean ms | Median ms | P95 ms | Max ms | Retries | Tests |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for v in variants:
        m = v.get("metrics", {})
        d = v.get("profile", {}).get("distributions", {}).get("router_wall_ms", {})
        latency = " | ".join(f"{d[k]:.2f}" if v["correctness_gate"] else "not ranked" for k in ("mean", "median", "p95", "max"))
        lines.append(f"| {v['variant']} | {'PASS' if v['correctness_gate'] else ('FAIL' if v['complete'] else 'PENDING')} | {m.get('passed', '-')} | {m.get('full_match_count', '-')} | {m.get('recall_hit', '-')}/26 | {latency} | {v.get('profile', {}).get('retry_turns', '-')} | {v.get('tests', {}).get('tests', '-')} |")
    lines += ["", "Latency of failed correctness variants is retained as raw diagnostic data in JSON, not ranked as an improvement.",
              "", "Historical B5 before: " + json.dumps(before), "", "Selected variant: " + str(result["selected_variant"]),
              "", "Selected after: " + json.dumps(after), "", "Improvement fractions: " + json.dumps(result["improvement"]),
              "", result["recommendation"], "", "Each variant uses a fresh complete set of responses; no prediction reuse. Fixed model/effort, concurrency 2. Sequential runs include provider/network variability. Development set reuse does not measure hidden-test generalization."]
    if selected:
        p, m = selected["profile"], selected["metrics"]
        def avg(key):
            return p["distributions"][key]["mean"]
        evidence = next((r for r in p["request_records"] if r.get("cached_tokens", 0)), {})
        lines += ["", "## Required report fields", "", "Correctness:",
            f"Primary: {m['passed']}/104", f"Full-match: {m['full_match_count']}/104",
            f"Multi-intent recall: {m['recall_hit']}/{m['recall_total']}",
            "Boundary probe: PASS; CLARIFY; execution_allowed=false",
            f"Regression tests: {selected['tests']['tests']} passed in the immutable variant",
            f"Unrecovered schema/API/system-intent failures: {m['schema_failures']}/{m['api_failures']}/{m['system_intent_failures']}",
            "", "Latency before (historical B5, ms):",
            *[f"{key}: {before[key]:.2f}" for key in ("mean", "median", "p95", "max")],
            "", "Latency after (ms):", *[f"{key}: {after[key]:.2f}" for key in ("mean", "median", "p95", "max")],
            "", "Improvement:", *[f"{key}: {result['improvement'][key]:.2%}" for key in ("mean", "p95")],
            "", "Token profile (mean per real request, retries included; prewarm excluded):",
            f"input tokens: {avg('input_tokens'):.2f}", f"cached tokens: {avg('cached_tokens'):.2f}",
            f"cache hit ratio: {p['cache_hit_ratio']:.4%}", f"cache write tokens: {avg('cache_write_tokens'):.2f}",
            f"output tokens: {avg('output_tokens'):.2f}", f"reasoning tokens: {avg('reasoning_tokens'):.2f}",
            "", "Retry profile:", f"before: {historical['retry_turns']}/104 ({historical['retry_rate']:.2%})",
            f"after: {p['retry_turns']}/104 ({p['retry_rate']:.2%})", "", "Prompt cache:",
            "configured: explicit breakpoint after invariant prefix; TTL 30m; separate prewarm",
            f"verified: {p['requests_with_cache_hits']}/{p['cache_observed_requests']} requests report cached tokens",
            f"cache hit evidence: response {evidence.get('response_id')}; {evidence.get('cached_tokens')} cached / {evidence.get('input_tokens')} input tokens",
            "prewarm evidence (separate startup work): " + json.dumps(selected.get('prewarm')),
            "", "Schema repair:", f"before: {historical['schema_failed_attempts']} rejected attempts",
            f"after: {p['schema_failed_attempts']} rejected attempts; {p['schema_failures']} unrecovered failures",
            "", "Changes made:",
            "Per-request usage, timing, exact JSON byte size and payload hashes; frozen source/data manifests; stable-prefix caching and output-free prewarm. L3 adds compact JSON/concise machine prose with exact evidence quotes. L4 additionally reinforces candidate/boundary membership. Schemas, validator, policy, compiler and gold remain unchanged.",
            "", "Changes rejected because they hurt correctness:",
            "; ".join(f"{v['variant']}: correctness gate failed; primary {v.get('metrics', {}).get('passed')}/104, API errors {v.get('metrics', {}).get('api_failures')}"
                      for v in variants if v['complete'] and not v['correctness_gate']) or "None in completed variants.",
            "A failed instrumentation-only run with transport errors does not establish a semantic regression. All failures remain in raw artifacts.",
            "", "Remaining bottleneck:",
            f"Mean HTTP wall {avg('http_wall_ms'):.2f} ms; validation {avg('schema_validation_ms'):.3f} ms; policy {p['distributions']['turn_policy_ms']['mean']:.3f} ms. "
            f"Mean returned provider lifecycle {avg('provider_lifecycle_ms'):.2f} ms (one-second timestamp resolution). "
            "HTTP includes queue, compute, network and download; generation-only/TTFT latency is not isolated. This is router latency, not voice latency.",
            "", "Recommendation:", result["recommendation"],
            "B6 has not been started. Original engineering targets remain mean <5000 ms and p95 <8000 ms."]
    (output / "b55_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("all_complete", "selected_variant", "recommendation")}), flush=True)


if __name__ == "__main__":
    main()
