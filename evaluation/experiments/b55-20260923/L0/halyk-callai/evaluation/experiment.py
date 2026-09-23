"""Freeze and execute one B5.5 variant without copying local credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config.settings import Settings


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()
            and not any(part in {"__pycache__", ".pytest_cache", "results"} for part in p.relative_to(root).parts)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("variant", choices=["L0", "L1", "L2", "L3", "L4"])
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    settings = Settings.load()
    settings.require_api_key()
    target = ROOT / "evaluation" / "experiments" / args.batch / args.variant
    target.mkdir(parents=True, exist_ok=False)
    source = target / "halyk-callai"
    source.mkdir()
    for name in ("backend", "scripts"):
        shutil.copytree(ROOT / name, source / name, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (source / "evaluation").mkdir()
    for path in (ROOT / "evaluation").glob("*.py"):
        shutil.copy2(path, source / "evaluation" / path.name)
    for name in ("pyproject.toml", "requirements.lock"):
        shutil.copy2(ROOT / name, source / name)
    shutil.copytree(settings.dataset_path, target / "case_2" / "voice_router_dataset",
                    ignore=shutil.ignore_patterns("__pycache__"))
    manifest = {"variant": args.variant, "created_at": datetime.now(timezone.utc).isoformat(),
                "source_hashes": hashes(source), "dataset_hashes": hashes(target / "case_2"),
                "model": settings.model, "concurrency": settings.eval_concurrency,
                "base_url": settings.base_url}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    env = {**os.environ, "OPENAI_API_KEY": settings.api_key, "OPENAI_BASE_URL": settings.base_url,
           "CALLAI_MODEL": settings.model, "CALLAI_EVAL_CONCURRENCY": str(settings.eval_concurrency),
           "CALLAI_TIMEOUT_SECONDS": str(settings.timeout_seconds), "PYTHONIOENCODING": "utf-8",
           "PYTHONPATH": str(source / "backend") + os.pathsep + str(source)}
    env.pop("CALLAI_DATASET_PATH", None)  # byte-identical frozen copy, including test defaults
    steps = {}
    commands = [("tests", ["-m", "pytest", "-q", "--junitxml=../tests.xml"]),
                ("official", ["evaluation/run_official.py"]),
                ("boundary", ["evaluation/run_boundary_probe.py"])]
    for name, command in commands:
        print(f"{args.variant}: {name}", flush=True)
        with (target / (name + ".log")).open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, *command], cwd=source, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end="", flush=True)
            steps[name] = process.wait()
        if name == "tests" and steps[name]:
            break
    unchanged = hashes(source) == manifest["source_hashes"] and hashes(target / "case_2") == manifest["dataset_hashes"]
    result = {"steps": steps, "snapshot_unchanged": unchanged}
    (target / "execution.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    return 0 if unchanged and len(steps) == 3 and not any(steps.values()) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
