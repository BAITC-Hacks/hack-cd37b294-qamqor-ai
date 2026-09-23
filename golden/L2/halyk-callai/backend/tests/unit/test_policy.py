import pytest
from app.policy.engine import PolicyEngine
from app.policy.rules import reanalysis_reason
from app.router.schemas import RouterInput, RouterProposal, Turn


def make_proposal(ids=None, system=None, relation="new", checks=None):
    return RouterProposal.model_validate(dict(
        scenarios=ids or [], alternatives=[], system_intent=system,
        evidence=[dict(evidence_id="e1", fact="test evidence", source_type="user_turn", source_id="t1", quote="test", polarity="positive", supersedes=None)],
        boundary_checks=checks or [], slot_updates=[], input_language="ru", response_language="ru", confidence=0.1,
        topic_relation=relation, clarification_question="Какой вопрос?" if system == "SYS_UNCLEAR" else None, reason="Tested policy transition"))


def context(active=None, stack=None):
    return RouterInput(current_user_turn=Turn(turn_id="t1", role="user", text="test"), active_scenario=active, topic_stack=stack or [])


def check(scenario="SC26", status="missing"):
    return dict(scenario_id=scenario, neighbor_id="SC30", distinguishing_fact="issued", status=status, source_rule=None, evidence_ids=[])


@pytest.mark.parametrize("ids,active,stack,relation,action,next_active,next_stack", [
    (["SC33"], None, [], "new", "ROUTE", "SC33", []),
    (["SC33"], "SC33", [], "continue", "STAY", "SC33", []),
    (["SC22"], "SC10", [], "new", "SWITCH", "SC22", ["SC10"]),
    (["SC10"], "SC22", ["SC10"], "restore", "RESTORE", "SC10", ["SC22"]),
    (["SC22"], "SC22", ["SC10"], "complete", "RESTORE", "SC10", []),
    (["SC22"], "SC22", [], "complete", "STAY", None, []),
    (["SC10"], "SC22", [], "restore", "CLARIFY", "SC22", []),
    (["SC37"], None, [], "new", "HANDOFF", "SC37", []),
])
def test_transitions(dataset, ids, active, stack, relation, action, next_active, next_stack):
    request = context(active, stack)
    before = request.model_dump()
    decision = PolicyEngine(dataset).decide(make_proposal(ids, relation=relation), request)
    assert (decision.action, decision.next_active_scenario, decision.next_topic_stack) == (action, next_active, next_stack)
    assert request.model_dump() == before
    assert decision.execution_allowed is False


@pytest.mark.parametrize("system,action", [("SYS_UNCLEAR", "CLARIFY"), ("SYS_OUT_OF_SCOPE", "RESPOND_OUT_OF_SCOPE"), ("SYS_GOODBYE", "END")])
def test_system_intents(dataset, system, action):
    decision = PolicyEngine(dataset).decide(make_proposal(system=system), context("SC22", ["SC10"]))
    assert decision.action == action
    assert decision.official_ids() == [system]
    if action != "END":
        assert decision.next_active_scenario == "SC22"


def test_urgent_first_not_high_first(dataset):
    result = PolicyEngine(dataset).decide(make_proposal(["SC33", "SC19", "SC15", "SC11"]), context())
    assert result.scenarios == ["SC15", "SC11", "SC33", "SC19"]


def test_missing_evidence_clarifies_and_never_retries(dataset):
    proposal = make_proposal(["SC26"], checks=[check()])
    result = PolicyEngine(dataset).decide(proposal, context("SC22"))
    assert result.action == "CLARIFY" and result.next_active_scenario == "SC22"
    assert reanalysis_reason(proposal) is None


def test_persistent_conflict_clarifies_after_bounded_reanalysis(dataset):
    proposal = make_proposal(["SC26"], checks=[check(status="conflicting")])
    assert reanalysis_reason(proposal)
    assert PolicyEngine(dataset).decide(proposal, context()).action == "CLARIFY"


def test_secondary_missing_fact_does_not_block_supported_urgent(dataset):
    proposal = make_proposal(["SC26", "SC11"], checks=[check()])
    decision = PolicyEngine(dataset).decide(proposal, context())
    assert decision.scenarios == ["SC11"] and decision.deferred_scenarios == ["SC26"]


def test_confidence_alone_never_changes_route(dataset):
    proposal = make_proposal(["SC33"])
    assert reanalysis_reason(proposal) is None
    assert PolicyEngine(dataset).decide(proposal, context()).scenarios == ["SC33"]


def test_pending_action_prevents_premature_topic_completion(dataset):
    request = context("SC02", ["SC33"])
    request.pending_action = "create_policy"
    result = PolicyEngine(dataset).decide(make_proposal(["SC02"], relation="complete"), request)
    assert result.action == "CLARIFY"
    assert result.next_active_scenario == "SC02"
    assert result.next_topic_stack == ["SC33"]
