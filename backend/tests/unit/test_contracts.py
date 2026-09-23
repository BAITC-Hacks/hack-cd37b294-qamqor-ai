import copy
import pytest
from pydantic import ValidationError
from app.router.schemas import RouterInput, Turn
from app.router.validator import validate_proposal, ProposalError, output_schema


@pytest.fixture
def request_input():
    return RouterInput(current_user_turn=Turn(turn_id="t1", role="user", text="Хочу узнать адрес офиса в Алматы"))


@pytest.fixture
def payload():
    return dict(scenarios=["SC33"], alternatives=[], system_intent=None,
                evidence=[dict(evidence_id="e1", fact="Wants office address", source_type="user_turn", source_id="t1",
                               quote="адрес офиса", polarity="positive", supersedes=None)],
                boundary_checks=[], slot_updates=[], input_language="ru", response_language="ru", confidence=0.9,
                topic_relation="new", clarification_question=None, reason="Office location request")


def test_valid_proposal(dataset, request_input, payload):
    assert validate_proposal(payload, dataset, request_input).scenarios == ["SC33"]


@pytest.mark.parametrize("change", [
    {"scenarios": ["SC99"]}, {"scenarios": ["SC33", "SC33"]}, {"confidence": 1.1},
    {"confidence": float("nan")}, {"confidence": "0.9"}, {"surprise": True},
    {"system_intent": "SYS_UNCLEAR"}, {"scenarios": [], "system_intent": "SYS_OOS"},
    {"evidence": []}, {"alternatives": ["SC33"]},
])
def test_invalid_proposals_rejected(dataset, request_input, payload, change):
    payload.update(change)
    with pytest.raises((ValidationError, ProposalError)):
        validate_proposal(payload, dataset, request_input)


def test_fabricated_backend_source_rejected(dataset, request_input, payload):
    payload["evidence"][0].update(source_type="backend", source_id="P-invented", quote=None)
    with pytest.raises(ProposalError, match="invented evidence"):
        validate_proposal(payload, dataset, request_input)


def test_fabricated_quote_rejected(dataset, request_input, payload):
    payload["evidence"][0]["quote"] = "У меня есть КАСКО"
    with pytest.raises(ProposalError, match="quote"):
        validate_proposal(payload, dataset, request_input)


@pytest.mark.parametrize("slot,value", [("invented", "x"), ("city", "Paris"), ("phone", "123"), ("payment_date", "2026-02-30"), ("injured", "false")])
def test_bad_slots_rejected(dataset, request_input, payload, slot, value):
    payload["slot_updates"] = [dict(slot_id=slot, raw_value=value, normalized_value=value, source_turn_id="t1", topic_id="SC33")]
    with pytest.raises(ValueError):
        validate_proposal(payload, dataset, request_input)


def test_schema_uses_real_enum_and_required_properties(dataset):
    schema = output_schema(dataset)
    assert len(schema["properties"]["scenarios"]["items"]["enum"]) == 40
    for node in [schema, *schema["$defs"].values()]:
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node["properties"])


def test_superseded_evidence_is_not_usable(dataset, request_input, payload):
    old = copy.deepcopy(payload["evidence"][0])
    payload["evidence"].append({**old, "evidence_id": "e2", "supersedes": "e1"})
    payload["boundary_checks"] = [dict(scenario_id="SC33", neighbor_id="SC20", distinguishing_fact="office not inspection", status="supported", source_rule=None, evidence_ids=["e1"])]
    with pytest.raises(ProposalError, match="superseded"):
        validate_proposal(payload, dataset, request_input)


@pytest.mark.parametrize("status", ["supported", "missing", "conflicting"])
def test_reverse_official_boundary_is_anchored_without_changing_evidence(dataset, payload, status):
    from app.catalog.boundaries import compile_boundaries
    from app.policy.engine import PolicyEngine
    source = next(r for r in compile_boundaries(dataset) if r["scenario_id"] == "SC01" and r["neighbor_id"] == "SC02")
    request = RouterInput(current_user_turn=Turn(turn_id="t1", role="user", text="Оформляйте полис"))
    payload["scenarios"] = ["SC02"]
    payload["evidence"][0].update(fact="Requests issuance", quote="Оформляйте полис")
    payload["boundary_checks"] = [dict(scenario_id="SC01", neighbor_id="SC02", distinguishing_fact="Request to issue rather than quote",
                                       status=status, source_rule=source["rule_id"], evidence_ids=["e1"])]
    result = validate_proposal(payload, dataset, request)
    check = result.boundary_checks[0]
    assert (check.scenario_id, check.neighbor_id) == ("SC02", "SC01")
    assert check.status == status and check.source_rule == source["rule_id"]
    assert check.evidence_ids == ["e1"] and result.scenarios == ["SC02"]
    assert payload["boundary_checks"][0]["scenario_id"] == "SC01"  # raw output intact
    if status != "supported":
        assert PolicyEngine(dataset).decide(result, request).action == "CLARIFY"


def test_reverse_boundary_without_valid_source_is_not_silently_accepted(dataset, request_input, payload):
    payload["boundary_checks"] = [dict(scenario_id="SC20", neighbor_id="SC33", distinguishing_fact="different locations",
                                       status="supported", source_rule=None, evidence_ids=["e1"])]
    with pytest.raises(ProposalError, match="candidate"):
        validate_proposal(payload, dataset, request_input)


def test_boundary_source_for_unrelated_pair_rejected(dataset, request_input, payload):
    payload["boundary_checks"] = [dict(scenario_id="SC20", neighbor_id="SC33", distinguishing_fact="different locations",
                                       status="supported", source_rule="scenarios.json#/scenarios/0/not_this_if/0", evidence_ids=["e1"])]
    with pytest.raises(ProposalError, match="does not match pair"):
        validate_proposal(payload, dataset, request_input)


def test_system_result_cannot_emit_boundary_without_business_candidate(dataset, request_input, payload):
    payload.update(scenarios=[], system_intent="SYS_OUT_OF_SCOPE", topic_relation="none")
    payload["boundary_checks"] = [dict(scenario_id="SC33", neighbor_id="SYS_OUT_OF_SCOPE",
        distinguishing_fact="location request versus unsupported service", status="supported",
        source_rule=None, evidence_ids=["e1"])]
    with pytest.raises(ProposalError, match="candidate"):
        validate_proposal(payload, dataset, request_input)
    # A genuine competing business interpretation can still carry its evidence check.
    payload["alternatives"] = ["SC33"]
    assert validate_proposal(payload, dataset, request_input).boundary_checks[0].scenario_id == "SC33"


def test_system_result_without_business_candidates_keeps_evidence(dataset, request_input, payload):
    payload.update(scenarios=[], system_intent="SYS_OUT_OF_SCOPE", topic_relation="none")
    validated = validate_proposal(payload, dataset, request_input)
    assert validated.boundary_checks == [] and validated.evidence[0].quote == "адрес офиса"
