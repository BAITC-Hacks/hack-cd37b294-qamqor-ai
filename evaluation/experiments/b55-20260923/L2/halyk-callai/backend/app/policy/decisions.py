from typing import Literal
from pydantic import Field
from app.router.schemas import StrictModel


class PolicyDecision(StrictModel):
    action: Literal["ROUTE", "STAY", "SWITCH", "RESTORE", "CLARIFY", "HANDOFF", "RESPOND_OUT_OF_SCOPE", "END"]
    scenarios: list[str] = Field(default_factory=list)
    system_intent: str | None = None
    next_active_scenario: str | None = None
    next_topic_stack: list[str] = Field(default_factory=list)
    deferred_scenarios: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    handoff_queue: str | None = None
    reason: str
    # Routing never authorizes a backend mutation. B8 owns execution checks.
    execution_allowed: Literal[False] = False

    def official_ids(self) -> list[str]:
        return self.scenarios or ([self.system_intent] if self.system_intent else [])
