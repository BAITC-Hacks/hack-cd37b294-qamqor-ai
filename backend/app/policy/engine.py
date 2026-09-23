from app.catalog.loader import Dataset
from app.router.schemas import RouterInput, RouterProposal
from app.policy.decisions import PolicyDecision


class PolicyEngine:
    def __init__(self, dataset: Dataset):
        self.dataset = dataset

    def decide(self, proposal: RouterProposal, request: RouterInput) -> PolicyDecision:
        unchanged = dict(next_active_scenario=request.active_scenario, next_topic_stack=list(request.topic_stack))

        def clarify(reason):
            return PolicyDecision(action="CLARIFY", system_intent="SYS_UNCLEAR", **unchanged,
                                  clarification_question=proposal.clarification_question or (
                                      "Нақты қай мәселені шешкіңіз келеді?" if proposal.response_language == "kk"
                                      else "Уточните, какой вопрос нужно решить?"), reason=reason)

        if proposal.system_intent:
            if proposal.system_intent == "SYS_UNCLEAR":
                return clarify("Insufficient evidence; preserve active task")
            if proposal.system_intent == "SYS_OUT_OF_SCOPE":
                return PolicyDecision(action="RESPOND_OUT_OF_SCOPE", system_intent=proposal.system_intent,
                                      reason="Outside canonical services; no automatic operator transfer", **unchanged)
            if proposal.system_intent == "SYS_GOODBYE":
                return PolicyDecision(action="END", system_intent=proposal.system_intent, reason="Explicit end of conversation")
            raise ValueError("Unvalidated system intent")

        # Stable sort: urgent first, all other priorities retain mention order.
        ordered = sorted(proposal.scenarios, key=lambda s: self.dataset.scenarios[s]["priority"] != "urgent")
        unresolved = {b.scenario_id for b in proposal.boundary_checks
                      if b.status in {"missing", "conflicting"} and b.scenario_id in ordered}
        # An unambiguous urgent task must not be lost behind a missing fact in a secondary task.
        supported_urgent = [s for s in ordered if s not in unresolved and self.dataset.scenarios[s]["priority"] == "urgent"]
        if unresolved and not supported_urgent:
            return clarify("Missing or still-conflicting distinguishing evidence")
        deferred = [s for s in ordered if s in unresolved]
        ordered = [s for s in ordered if s not in unresolved]
        if not ordered:
            return clarify("No supported scenario")
        primary = ordered[0]
        stack = list(request.topic_stack)
        active = request.active_scenario

        if proposal.topic_relation == "complete":
            if request.pending_action:
                return clarify("Pending backend action cannot be completed by a routing proposal")
            if active is None or primary != active:
                return clarify("Completion must refer to the active task")
            if stack:
                target = stack.pop()
                return PolicyDecision(action="RESTORE", scenarios=ordered, next_active_scenario=target,
                                      next_topic_stack=stack, reason="Current task completed; resume previous unfinished task")
            return PolicyDecision(action="STAY", scenarios=ordered, next_active_scenario=None,
                                  reason="Current task completed; no previous task")

        if proposal.topic_relation == "restore":
            if primary not in stack:
                return clarify("Requested previous task is not in topic stack")
            stack.remove(primary)
            if active and active != primary and active not in stack:
                stack.append(active)
            action = "RESTORE"
        elif active == primary:
            action = "STAY"
        elif active:
            if active not in stack:
                stack.append(active)
            # Reopening an existing task should not leave a duplicate stack entry.
            if primary in stack:
                stack.remove(primary)
            action = "SWITCH"
        else:
            action = "ROUTE"

        handoff = self.dataset.scenarios[primary]["handoff"]
        queue = None
        if handoff and handoff["when"] == "always":
            action, queue = "HANDOFF", handoff["queue"]
        return PolicyDecision(action=action, scenarios=ordered, next_active_scenario=primary,
                              next_topic_stack=stack, deferred_scenarios=deferred,
                              clarification_question=proposal.clarification_question,
                              handoff_queue=queue, reason=proposal.reason)
