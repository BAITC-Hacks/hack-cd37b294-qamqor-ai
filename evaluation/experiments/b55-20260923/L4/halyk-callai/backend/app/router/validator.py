from __future__ import annotations

import re
from datetime import date
from app.catalog.loader import Dataset
from app.catalog.boundaries import compile_boundaries
from app.router.schemas import RouterInput, RouterProposal


class ProposalError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ProposalError(message)


def validate_slot_value(slot: dict, value):
    if value is None:
        return  # explicit unresolved value; not an executable parameter
    kind = slot["type"]
    if kind == "enum":
        require(any(type(value) is type(v) and value == v for v in slot["values"]), "invalid slot enum")
    elif kind == "integer":
        require(type(value) is int, "slot must be integer")
    elif kind == "boolean":
        require(type(value) is bool, "slot must be boolean")
    elif kind == "list":
        require(type(value) is list, "slot must be list")
    else:
        require(isinstance(value, str), "slot must be string")
        if kind == "date":
            require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), "date must be ISO YYYY-MM-DD")
            date.fromisoformat(value)
    if slot.get("pattern"):
        items = value if kind == "list" else [value]
        require(all(isinstance(v, str) and re.fullmatch(slot["pattern"], v) for v in items), "invalid slot format")


def validate_input(request: RouterInput, dataset: Dataset):
    require(request.active_scenario is None or request.active_scenario in dataset.scenarios, "invalid active scenario")
    require(set(request.topic_stack) <= set(dataset.scenarios), "invalid topic stack")
    require(request.pending_action is None or request.pending_action in dataset.actions, "invalid pending action")
    for update in request.current_slots:
        require(update.slot_id in dataset.slots, "unknown state slot")
        validate_slot_value(dataset.slots[update.slot_id], update.normalized_value)
    for records in (request.latest_backend_results, request.knowledge_records):
        require(len(records) == len({r.source_id for r in records}), "duplicate source record IDs")


def validate_proposal(payload: dict, dataset: Dataset, request: RouterInput) -> RouterProposal:
    validate_input(request, dataset)
    proposal = RouterProposal.model_validate(payload)
    require(set(proposal.scenarios + proposal.alternatives) <= set(dataset.scenarios), "unknown business scenario")
    require(proposal.system_intent is None or proposal.system_intent in dataset.systems, "unknown system intent")
    sources = {
        "user_turn": {t.turn_id: t.text for t in [*request.history, request.current_user_turn] if t.role == "user"},
        "backend": {r.source_id: r.content for r in request.latest_backend_results},
        "knowledge_base": {r.source_id: r.content for r in request.knowledge_records},
    }
    evidence = {e.evidence_id: e for e in request.known_evidence}
    for item in proposal.evidence:
        require(item.evidence_id not in evidence, "evidence IDs must be new")
        require(item.source_id in sources[item.source_type], "invented evidence source")
        if item.source_type == "user_turn":
            require(bool(item.quote), "user evidence needs an exact quote")
        if item.quote:
            require(item.quote in sources[item.source_type][item.source_id], "evidence quote not present in source")
        if item.supersedes:
            require(item.supersedes in evidence, "superseded evidence does not exist")
        evidence[item.evidence_id] = item
    retired = {e.supersedes for e in evidence.values() if e.supersedes}
    rules = {r["rule_id"]: r for r in compile_boundaries(dataset)}
    for check in proposal.boundary_checks:
        candidates = proposal.scenarios + proposal.alternatives
        if check.source_rule:
            require(check.source_rule in rules, "invented boundary rule")
            rule = rules[check.source_rule]
            require({rule["scenario_id"], rule["neighbor_id"]} == {check.scenario_id, check.neighbor_id}, "rule does not match pair")
            # A canonical exception can point INTO the chosen scenario. Anchor the
            # comparison to that candidate, without changing the directional rule,
            # evidence, status or choice. No inference or LLM retry is needed.
            if check.scenario_id not in candidates and check.neighbor_id in candidates:
                check.scenario_id, check.neighbor_id = check.neighbor_id, check.scenario_id
        require(check.scenario_id in candidates, "boundary must concern a candidate")
        require(check.neighbor_id in dataset.scenarios or check.neighbor_id in dataset.systems, "unknown boundary neighbor")
        require(check.scenario_id != check.neighbor_id, "self boundary is invalid")
        require(set(check.evidence_ids) <= evidence.keys(), "unknown boundary evidence")
        require(not set(check.evidence_ids) & retired, "superseded evidence cannot support a boundary")
        if check.status == "supported":
            require(bool(check.evidence_ids), "supported boundary requires evidence")
    seen_slots = set()
    for update in proposal.slot_updates:
        require(update.slot_id in dataset.slots, "unknown slot ID")
        require(update.source_turn_id in sources["user_turn"], "unknown slot source")
        key = (update.topic_id, update.slot_id)
        require(key not in seen_slots, "duplicate slot updates")
        seen_slots.add(key)
        require(update.topic_id is None or update.topic_id in proposal.scenarios + request.topic_stack + ([request.active_scenario] if request.active_scenario else []), "unknown slot topic")
        validate_slot_value(dataset.slots[update.slot_id], update.normalized_value)
    return proposal


def output_schema(dataset: Dataset) -> dict:
    """Embed canonical enums into the schema sent to the provider."""
    schema = RouterProposal.model_json_schema()
    props = schema["properties"]
    for name in ("scenarios", "alternatives"):
        props[name]["items"]["enum"] = list(dataset.scenarios)
    props["system_intent"] = {"anyOf": [{"type": "string", "enum": list(dataset.systems)}, {"type": "null"}]}
    defs = schema["$defs"]
    defs["SlotUpdate"]["properties"]["slot_id"]["enum"] = list(dataset.slots)
    defs["BoundaryCheck"]["properties"]["scenario_id"]["enum"] = list(dataset.scenarios)
    defs["BoundaryCheck"]["properties"]["neighbor_id"]["enum"] = [*dataset.scenarios, *dataset.systems]
    return schema
