from __future__ import annotations

from collections import Counter, defaultdict
from math import ceil
from statistics import mean


def percentile95(values):
    return sorted(values)[max(0, ceil(0.95 * len(values)) - 1)] if values else None


def summarize(utterances: list[dict], records: list[dict]) -> dict:
    """Diagnostics supplement, never replace the original evaluate.py output."""
    by_id = {r["id"]: r for r in records}
    primary = full = recall_hit = recall_total = system_errors = 0
    errors, pairs = [], Counter()
    per_scenario, groups = defaultdict(Counter), defaultdict(Counter)
    for u in utterances:
        record = by_id.get(u["id"], {})
        expected, got = u["expected"], record.get("prediction", [])
        hit = bool(got) and got[0] == expected[0]
        exact = set(got) == set(expected)
        primary += int(hit)
        full += int(exact)
        for group in (f"lang={u['lang']}", f"type={u['type']}"):
            groups[group].update(total=1, primary=int(hit), full_match=int(exact))
        if u["type"] == "multi_intent":
            recall_hit += len(set(expected) & set(got))
            recall_total += len(expected)
        exp_sys = {s for s in expected if s.startswith("SYS_")}
        got_sys = {s for s in got if s.startswith("SYS_")}
        wrong_system = exp_sys != got_sys
        system_errors += int(wrong_system)
        for sid in expected:
            per_scenario[sid].update(total=1, missed=int(sid not in got), primary_error=int(not hit))
        if not hit:
            pairs[(expected[0], got[0] if got else "NO_PREDICTION")] += 1
        if not exact or not hit:
            categories = []
            if record.get("error_kind") == "SCHEMA_ERROR":
                categories.append("SCHEMA_ERROR")
            if wrong_system:
                categories.append("WRONG_SYSTEM_INTENT")
            if "SYS_UNCLEAR" in got and "SYS_UNCLEAR" not in expected:
                categories.append("UNNECESSARY_CLARIFICATION")
            if set(expected) - set(got):
                categories.append("MISSED_INTENT")
            if set(got) - set(expected):
                categories.append("EXTRA_INTENT")
            if not hit:
                categories.append("WRONG_ROUTE")
            proposal = record.get("proposal") or {}
            checks = proposal.get("boundary_checks", [])
            if any(c["status"] == "missing" for c in checks):
                categories.append("INSUFFICIENT_EVIDENCE")
            if checks and not hit:
                categories.append("BAD_BOUNDARY_DECISION")
            errors.append({"id": u["id"], "text": u["text"], "expected": expected, "predicted": got,
                           "categories": categories, "technical_error": record.get("error_kind")})
    latencies = [r["latency_ms"] for r in records if r.get("attempts")]
    schema_attempts = sum(a.get("schema_valid") is False for r in records for a in r.get("attempts", []))
    return {
        "total": len(utterances), "attempted": len(records), "passed": primary,
        "failed": len(utterances) - primary, "primary_accuracy": primary / len(utterances) if utterances else None,
        "full_match_count": full, "full_match": full / len(utterances) if utterances else None,
        "recall_hit": recall_hit, "recall_total": recall_total, "recall": recall_hit / recall_total if recall_total else None,
        "top_confusion_pairs": [{"expected": a, "predicted": b, "count": n} for (a, b), n in pairs.most_common()],
        "schema_failures": sum(r.get("error_kind") == "SCHEMA_ERROR" for r in records),
        "schema_failed_attempts": schema_attempts,
        "system_intent_failures": system_errors,
        "api_failures": sum(r.get("error_kind") == "API_ERROR" for r in records),
        "average_router_latency_ms": mean(latencies) if latencies else None,
        "p95_router_latency_ms": percentile95(latencies),
        "latency_sample_count": len(latencies),
        "latency_definition": "Per utterance wall time of routing including shared-budget retry, excluding policy; nearest-rank p95; errors included",
        "per_scenario": dict(per_scenario), "groups": dict(groups), "errors": errors,
    }


def markdown(report: dict) -> str:
    m = report.get("metrics") or {}
    def value(key):
        v = m.get(key)
        return "not measured" if v is None else str(v)
    return "\n".join([
        "BUILD STATUS", "", f"Status: {report['status']}",
        f"Official examples: {report['official_examples']}",
        f"Passed: {value('passed')}", f"Failed: {value('failed')}",
        f"Exact/full-match: {value('full_match_count')} / {report['official_examples']} ({value('full_match')})",
        f"Recall: {value('recall')} (hits {value('recall_hit')} / {value('recall_total')})", "",
        f"Top confusion pairs: {value('top_confusion_pairs')}",
        f"Schema failures: {value('schema_failures')}",
        f"System-intent failures: {value('system_intent_failures')}", "",
        f"Average router latency: {value('average_router_latency_ms')} ms",
        f"P95 router latency: {value('p95_router_latency_ms')} ms", "",
        "Files changed: see README.md and BUILD_LOG.md; per-run code hashes in metadata.json",
        "Tests executed: see tests.xml and BUILD_LOG.md; tests are not model accuracy",
        f"Known blockers: {report.get('blocker') or 'none'}",
        "Next highest-impact fix: " + ("Configure real API access and run all official examples" if not m else "Review measured error categories before modifying routing"),
        "Passed/Failed refer to primary scenario correctness. Full-match uses set equality.",
        "This baseline scores policy decisions, not raw proposals. No synthetic results are included.",
    ]) + "\n"
