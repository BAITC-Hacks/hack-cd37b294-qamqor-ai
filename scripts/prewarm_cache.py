"""Optional developer operation: prime invariant routing context, never route a user."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.catalog.loader import checked_dataset
from app.config.settings import Settings
from app.router.llm import LLMRouter


async def main():
    settings = Settings.load()
    dataset = checked_dataset(settings.dataset_path)
    started = time.perf_counter()
    async with httpx.AsyncClient() as client:
        router = LLMRouter(dataset, settings, client)
        try:
            result = await router.prewarm()
        except httpx.HTTPError as exc:
            result = {"passed": False, "error_kind": type(exc).__name__,
                      "http_wall_ms": (time.perf_counter() - started) * 1000}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    directory = ROOT / "evaluation" / "results" / ("cache_prewarm_" + stamp)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "raw.jsonl").write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {key: result.get(key) for key in ("passed", "http_status", "http_wall_ms", "input_tokens", "cached_tokens",
                                               "cache_write_tokens", "output_tokens", "error_kind")}
    summary.update(model=settings.model, source_hashes=dataset.hashes, artifact=str(directory))
    (directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
