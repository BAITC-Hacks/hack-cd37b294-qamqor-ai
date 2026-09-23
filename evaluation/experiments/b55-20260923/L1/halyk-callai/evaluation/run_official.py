from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
import httpx
from app.catalog.loader import checked_dataset, load_dataset
from app.config.settings import Settings, ConfigurationError
from app.catalog.compiler import compile_catalog, catalog_hash
from app.router.prompt import prompt_hash
from app.router.llm import LLMRouter
from app.router.schemas import RouterInput, Turn
from app.policy.engine import PolicyEngine
from app.policy.rules import reanalysis_reason
from evaluation.report import summarize, markdown


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def configure_console(stream=None):
    """The official scorer can print Kazakh text outside Windows cp1251."""
    stream = stream if stream is not None else sys.stdout
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")


async def collect(dataset, settings, run_dir):
    records = []
    semaphore = asyncio.Semaphore(settings.eval_concurrency)
    stop = asyncio.Event()
    policy = PolicyEngine(dataset)
    async with httpx.AsyncClient() as client:
        router = LLMRouter(dataset, settings, client)
        async def one(example):
            async with semaphore:
                if stop.is_set():
                    return
                # Only the utterance is sent to the router, never expected/type/lang.
                request = RouterInput(current_user_turn=Turn(turn_id="turn-1", role="user", text=example["text"]))
                result = await router.route(request, reanalysis_reason)
                tick = time.perf_counter()
                decision = policy.decide(result.proposal, request) if result.proposal else None
                policy_ms = (time.perf_counter() - tick) * 1000
                if result.attempts:
                    result.attempts[-1]["policy_latency_ms"] = policy_ms if decision else None
                record = {
                    "id": example["id"], "prediction": decision.official_ids() if decision else [],
                    "proposal": result.proposal.model_dump() if result.proposal else None,
                    "decision": decision.model_dump() if decision else None,
                    "latency_ms": result.latency_ms, "policy_latency_ms": policy_ms,
                    "retry_count": result.retry_count,
                    "attempts": result.attempts, "error": result.error, "error_kind": result.error_kind,
                }
                records.append(record)
                # Append each completed real call immediately; survive interruption.
                with (run_dir / "raw.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"{len(records)}/{len(dataset.documents['dev_utterances.json']['utterances'])} {example['id']} {record['prediction']} {result.error_kind or 'OK'}", flush=True)
                if any(a.get("http_status") in {401, 403, 404} for a in result.attempts):
                    stop.set()
        await asyncio.gather(*(one(u) for u in dataset.documents["dev_utterances.json"]["utterances"]))
    return sorted(records, key=lambda r: r["id"])


def main(argv=None):
    configure_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "results")
    args = parser.parse_args(argv)
    settings = Settings.load(args.env_file)
    dataset = checked_dataset(settings.dataset_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_dir = args.output_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    catalog = compile_catalog(dataset)
    code_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for parent in (ROOT / "backend" / "app", ROOT / "evaluation")
                   for p in parent.rglob("*.py")}
    metadata = {"run_id": stamp, "model": settings.model, "base_url": settings.base_url,
                "reasoning": ["low", "medium_on_bounded_retry"], "temperature": "provider default; not supplied",
                "concurrency": settings.eval_concurrency, "python": platform.python_version(),
                "catalog_hash": catalog_hash(catalog), "prompt_hash": prompt_hash(catalog),
                "source_hashes": dataset.hashes, "code_hashes": code_hashes}
    write_json(run_dir / "metadata.json", metadata)
    report = {"status": "blocked", "official_examples": len(dataset.documents["dev_utterances.json"]["utterances"]),
              "metrics": None, "metadata": metadata, "run_directory": str(run_dir), "blocker": None}
    try:
        settings.require_api_key()
    except ConfigurationError as exc:
        report["blocker"] = str(exc)
    else:
        records = asyncio.run(collect(dataset, settings, run_dir))
        predictions = {r["id"]: r["prediction"] for r in records}
        write_json(run_dir / "predictions.json", predictions)
        if load_dataset(settings.dataset_path).hashes != dataset.hashes:
            report["blocker"] = "Official source hashes changed during evaluation; results invalidated"
        elif len(records) != report["official_examples"]:
            report["blocker"] = f"API access failure stopped run after {len(records)} examples. Full baseline not measured."
        else:
            # Execute the original on-disk scorer as a separate process, unmodified.
            completed = subprocess.run(
                [sys.executable, str(dataset.path / "evaluate.py"), str((run_dir / "predictions.json").resolve()),
                 str(dataset.path / "dev_utterances.json")],
                capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            (run_dir / "official_stdout.txt").write_text(completed.stdout, encoding="utf-8")
            (run_dir / "official_stderr.txt").write_text(completed.stderr, encoding="utf-8")
            if completed.returncode:
                report["blocker"] = f"Official scorer failed (exit {completed.returncode})"
            else:
                report.update(status="executed", metrics=summarize(dataset.documents["dev_utterances.json"]["utterances"], records))
                print(completed.stdout)
    write_json(run_dir / "baseline.json", report)
    (run_dir / "baseline.md").write_text(markdown(report), encoding="utf-8")
    write_json(args.output_dir / "last_attempt.json", report)
    # A later failed attempt must not overwrite an actual measured baseline.
    baseline_path = args.output_dir / "baseline.json"
    previous = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    if report["status"] == "executed" or previous.get("status") != "executed":
        write_json(args.output_dir / "baseline.json", report)
        (args.output_dir / "baseline.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return 0 if report["status"] == "executed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
