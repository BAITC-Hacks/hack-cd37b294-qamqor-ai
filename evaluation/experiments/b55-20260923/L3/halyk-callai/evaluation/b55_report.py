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
    eligible = [v for v in variants if v["correctness_gate"] and v["variant"] in {"L2", "L3", "L4"}]
    selected = min(eligible, key=lambda v: v["profile"]["distributions"]["router_wall_ms"]["mean"]) if eligible else None
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
    (output / "b55_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("all_complete", "selected_variant", "recommendation")}), flush=True)


if __name__ == "__main__":
    main()
