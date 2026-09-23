"""Re-score a complete saved REAL run, without making model requests."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from app.catalog.loader import checked_dataset
from app.config.settings import Settings
from evaluation.run_official import write_json, configure_console
from evaluation.report import summarize, markdown


def recover(run_dir: Path, dataset):
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    if metadata["source_hashes"] != dataset.hashes:
        raise ValueError("Official sources differ from the recorded inference run")
    records = [json.loads(line) for line in (run_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines() if line]
    expected_ids = {u["id"] for u in dataset.documents["dev_utterances.json"]["utterances"]}
    actual_ids = [r["id"] for r in records]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise ValueError("Recovery requires exactly one saved response per official example")
    known = set(dataset.scenarios) | set(dataset.systems)
    for record in records:
        if not record.get("attempts") or not set(record["prediction"]) <= known:
            raise ValueError("Invalid saved inference record")
    predictions = {r["id"]: r["prediction"] for r in records}
    target = run_dir / "predictions.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != predictions:
        raise ValueError("Saved predictions differ from raw inference; refusing to overwrite")
    write_json(target, predictions)
    completed = subprocess.run([sys.executable, str(dataset.path / "evaluate.py"), str(target.resolve()),
                                str(dataset.path / "dev_utterances.json")], capture_output=True, text=True,
                               encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if completed.returncode:
        raise RuntimeError(f"Official scorer exit {completed.returncode}")
    (run_dir / "official_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    report = {"status": "executed", "official_examples": len(expected_ids), "metadata": metadata,
              "metrics": summarize(dataset.documents["dev_utterances.json"]["utterances"], records),
              "blocker": None, "run_directory": str(run_dir.resolve()),
              "report_recovered_at": datetime.now(timezone.utc).isoformat(), "new_model_calls": 0}
    for path in (run_dir, run_dir.parent):
        write_json(path / "baseline.json", report)
        (path / "baseline.md").write_text(markdown(report), encoding="utf-8")
    write_json(run_dir.parent / "last_attempt.json", report)
    return report


def main():
    configure_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    report = recover(args.run_directory, checked_dataset(Settings.load().dataset_path))
    print(markdown(report))


if __name__ == "__main__":
    main()
