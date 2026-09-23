from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from app.catalog.loader import Dataset, DEFAULT_DATASET, checked_dataset
from app.catalog.boundaries import compile_boundaries


def compile_catalog(dataset: Dataset) -> dict:
    # No gold labels, dev text, dialog fixtures or example matching tables in the prompt.
    keys = ("scenario_id", "name", "description", "priority", "requires_identification",
            "slots", "actions", "requires_confirmation", "handoff")
    return {
        "as_of_date": dataset.as_of_date,
        "scenarios": [{k: sc[k] for k in keys} for sc in dataset.scenarios.values()],
        "system_intents": list(dataset.systems.values()),
        "boundary_rules": compile_boundaries(dataset),
        "slots": [{k: v for k, v in slot.items() if k != "prompt"} for slot in dataset.slots.values()],
        "not_offered": dataset.documents["knowledge_base.json"]["company"]["not_offered"],
    }


def compact_text(catalog: dict) -> str:
    return json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def catalog_hash(catalog: dict) -> str:
    return hashlib.sha256(compact_text(catalog).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path("data/compiled_catalog.json"))
    args = parser.parse_args()
    dataset = checked_dataset(args.dataset)
    catalog = compile_catalog(dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenarios": len(catalog["scenarios"]), "systems": len(catalog["system_intents"]),
                      "rules": len(catalog["boundary_rules"]), "characters": len(compact_text(catalog)),
                      "sha256": catalog_hash(catalog)}, indent=2))


if __name__ == "__main__":
    main()
