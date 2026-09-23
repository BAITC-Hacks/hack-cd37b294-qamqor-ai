"""Live check of the ambiguous example from BUILD_SPEC section 13; not official accuracy."""
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.catalog.compiler import compile_catalog
from app.catalog.loader import checked_dataset
from app.config.settings import Settings
from app.policy.engine import PolicyEngine
from app.policy.rules import reanalysis_reason
from app.router.llm import LLMRouter
from app.router.prompt import prompt_hash
from app.router.schemas import RouterInput, Turn
from evaluation.run_official import configure_console, write_json


async def probe():
    settings = Settings.load()
    dataset = checked_dataset(settings.dataset_path)
    request = RouterInput(current_user_turn=Turn(
        turn_id="spec-13", role="user", text="Ақша списали, бірақ полис келмеді"))
    async with httpx.AsyncClient() as client:
        result = await LLMRouter(dataset, settings, client).route(request, reanalysis_reason)
    tick = time.perf_counter()
    decision = PolicyEngine(dataset).decide(result.proposal, request) if result.proposal else None
    policy_ms = (time.perf_counter() - tick) * 1000
    if result.attempts:
        result.attempts[-1]["policy_latency_ms"] = policy_ms if decision else None
    passed = bool(decision and decision.action == "CLARIFY" and decision.clarification_question
                  and not decision.execution_allowed and result.error is None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    directory = ROOT / "evaluation" / "results" / ("boundary_probe_" + stamp)
    record = {"source": "BUILD_SPEC.md section 13", "official_evaluation": False,
              "model": settings.model, "source_hashes": dataset.hashes,
              "prompt_hash": prompt_hash(compile_catalog(dataset)),
              "code_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (ROOT / "backend" / "app").rglob("*.py")},
              "request": request.model_dump(), "passed": passed,
              "proposal": result.proposal.model_dump() if result.proposal else None,
              "decision": decision.model_dump() if decision else None,
              "latency_ms": result.latency_ms, "policy_latency_ms": policy_ms,
              "retry_count": result.retry_count, "error_kind": result.error_kind}
    write_json(directory / "result.json", record)
    (directory / "raw.jsonl").write_text(json.dumps(result.attempts, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "decision": record["decision"], "result": str(directory / "result.json")}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    configure_console()
    raise SystemExit(asyncio.run(probe()))
