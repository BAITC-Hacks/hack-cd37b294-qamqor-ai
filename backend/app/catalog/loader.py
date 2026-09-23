from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = PROJECT_ROOT / "golden" / "L2" / "case_2" / "voice_router_dataset"
JSON_FILES = ("scenarios.json", "slots.json", "actions.json", "knowledge_base.json",
              "mock_backend.json", "dev_utterances.json", "dialogs_sample.json")


class DatasetError(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DatasetError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class Dataset:
    path: Path
    documents: dict
    hashes: dict[str, str]

    @property
    def scenarios(self):
        return {s["scenario_id"]: s for s in self.documents["scenarios.json"]["scenarios"]}

    @property
    def systems(self):
        return {s["id"]: s for s in self.documents["scenarios.json"]["system_intents"]}

    @property
    def slots(self):
        return {s["name"]: s for s in self.documents["slots.json"]["slots"]}

    @property
    def actions(self):
        return {a["name"]: a for a in self.documents["actions.json"]["actions"]}

    @property
    def as_of_date(self):
        return self.documents["scenarios.json"]["meta"]["as_of_date"]


def load_dataset(path: Path | str = DEFAULT_DATASET) -> Dataset:
    path = Path(path).resolve()
    documents, hashes = {}, {}
    for name in (*JSON_FILES, "evaluate.py"):
        try:
            raw = (path / name).read_bytes()
            hashes[name] = hashlib.sha256(raw).hexdigest()
            if name.endswith(".json"):
                documents[name] = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
        except (OSError, ValueError) as exc:
            raise DatasetError(f"Cannot load {name}: {exc}") from exc
    return Dataset(path, documents, hashes)


def validate_dataset(ds: Dataset) -> dict:
    errors, warnings = [], []

    def require(ok, message):
        if not ok:
            errors.append(message)

    def ids(rows, field, label):
        values = [r.get(field) for r in rows]
        require(all(isinstance(v, str) and v for v in values), f"{label}: missing ID")
        require(len(values) == len(set(values)), f"{label}: duplicate IDs")
        return set(values)

    try:
        docs = ds.documents
        catalog = docs["scenarios.json"]
        scenario_ids = ids(catalog["scenarios"], "scenario_id", "scenarios")
        system_ids = ids(catalog["system_intents"], "id", "systems")
        slot_ids = ids(docs["slots.json"]["slots"], "name", "slots")
        action_ids = ids(docs["actions.json"]["actions"], "name", "actions")
        known = scenario_ids | system_ids
        require(scenario_ids == {f"SC{i:02}" for i in range(1, 41)}, "Expected canonical SC01..SC40")
        require(system_ids == {"SYS_UNCLEAR", "SYS_OUT_OF_SCOPE", "SYS_GOODBYE"}, "Unexpected system IDs")
        date.fromisoformat(ds.as_of_date)
        for name, doc in docs.items():
            require(doc["meta"]["as_of_date"] == ds.as_of_date, f"{name}: inconsistent reference date")
        queues = docs["actions.json"]["queues"]
        for sc in catalog["scenarios"]:
            sid = sc["scenario_id"]
            require(bool(sc["description"]), f"{sid}: empty definition")
            require(sc["priority"] in {"normal", "high", "urgent"}, f"{sid}: invalid priority")
            require(set(sc["slots"]["required"] + sc["slots"]["optional"]) <= slot_ids, f"{sid}: unknown slot")
            require(set(sc["actions"]) <= action_ids, f"{sid}: unknown action")
            for edge in sc["not_this_if"]:
                require(edge["use_instead"] in known, f"{sid}: unknown boundary target")
                require(bool(edge["condition"]), f"{sid}: empty boundary")
            if sc["handoff"]:
                require(sc["handoff"]["queue"] in queues, f"{sid}: unknown handoff queue")
            for lang in ("ru", "kk"):
                require(bool(sc["examples"][lang]), f"{sid}: missing {lang} examples")
            irreversible = any(ds.actions[a]["irreversible"] for a in sc["actions"] if a in ds.actions)
            require(not irreversible or sc["requires_confirmation"], f"{sid}: irreversible action without confirmation")
        for action in ds.actions.values():
            require(set(action["errors"]) <= set(docs["actions.json"]["error_codes"]), f"{action['name']}: unknown error")
            # Action inputs include backend IDs and alternatives (phone|iin), not only slots.
        backend = docs["mock_backend.json"]
        clients = ids(backend["clients"], "client_id", "clients")
        policies = ids(backend["policies"], "policy_number", "policies")
        ids(backend["claims"], "claim_number", "claims")
        ids(backend["payments"], "payment_id", "payments")
        products = set(docs["knowledge_base.json"]["products"])
        for p in backend["policies"]:
            require(p["client_id"] in clients, f"{p['policy_number']}: unknown client")
            require(p["product"] in products, f"{p['policy_number']}: unknown product")
            require(date.fromisoformat(p["start_date"]) <= date.fromisoformat(p["end_date"]), "Invalid policy dates")
        for collection in ("claims", "payments"):
            for record in backend[collection]:
                require(record["client_id"] in clients, f"{collection}: unknown client")
                require(record.get("policy_number") is None or record["policy_number"] in policies, f"{collection}: unknown policy")
                # An OGPO victim need not own the at-fault driver's policy.
        dev = docs["dev_utterances.json"]["utterances"]
        ids(dev, "id", "dev")
        for u in dev:
            require(bool(u["text"]), f"{u['id']}: empty text")
            require(bool(u["expected"]) and set(u["expected"]) <= known, f"{u['id']}: invalid gold ID")
            require(len(u["expected"]) == len(set(u["expected"])), f"{u['id']}: duplicate gold ID")
            require(u["lang"] in {"ru", "kk", "mixed"}, f"{u['id']}: invalid language")
        dialogs = docs["dialogs_sample.json"]["dialogs"]
        ids(dialogs, "dialog_id", "dialogs")
        for dialog in dialogs:
            require(dialog["client_id"] is None or dialog["client_id"] in clients, f"{dialog['dialog_id']}: unknown client")
            if len(dialog["turns"]) > 10:
                warnings.append(f"{dialog['dialog_id']}: {len(dialog['turns'])} messages; preserve original, count client turns separately")
            for turn in dialog["turns"]:
                require(turn["role"] in {"client", "bot"}, "Unknown dialog role")
                if turn["role"] == "client":
                    require(set(turn["scenarios"]) <= known, "Dialog: invalid scenario")
                    require(set(turn["slots"]) <= slot_ids, "Dialog: invalid slot")
                else:
                    for action in turn.get("actions", []):
                        require(action["name"] in action_ids, "Dialog: invalid action")
                        if "mode" in action:
                            require(action["mode"] in {"preview", "execute"}, "Dialog: invalid execution mode")
        counts = {"scenarios": len(scenario_ids), "system_intents": len(system_ids),
                  "slots": len(slot_ids), "actions": len(action_ids), "official_examples": len(dev), "dialogs": len(dialogs)}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        errors.append(f"Malformed dataset structure: {exc}")
        counts = {}
    return {"valid": not errors, "errors": errors, "warnings": warnings, "counts": counts,
            "sha256": ds.hashes, "dataset_path": str(ds.path)}


def checked_dataset(path: Path | str = DEFAULT_DATASET) -> Dataset:
    ds = load_dataset(path)
    report = validate_dataset(ds)
    if not report["valid"]:
        raise DatasetError("; ".join(report["errors"]))
    return ds
