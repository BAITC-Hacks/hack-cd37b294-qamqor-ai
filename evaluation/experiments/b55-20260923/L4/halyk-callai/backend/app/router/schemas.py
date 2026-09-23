from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class EvidenceItem(StrictModel):
    evidence_id: str
    fact: str = Field(min_length=1)
    source_type: Literal["user_turn", "backend", "knowledge_base"]
    source_id: str
    quote: str | None
    polarity: Literal["positive", "negative"]
    supersedes: str | None


class BoundaryCheck(StrictModel):
    scenario_id: str
    neighbor_id: str
    distinguishing_fact: str = Field(min_length=1)
    status: Literal["supported", "missing", "conflicting"]
    source_rule: str | None
    evidence_ids: list[str]


Scalar = str | int | float | bool | None


class SlotUpdate(StrictModel):
    slot_id: str
    raw_value: Scalar | list[Scalar]
    normalized_value: Scalar | list[Scalar]
    source_turn_id: str
    topic_id: str | None


class RouterProposal(StrictModel):
    scenarios: list[str]
    alternatives: list[str]
    system_intent: str | None
    evidence: list[EvidenceItem]
    boundary_checks: list[BoundaryCheck]
    slot_updates: list[SlotUpdate]
    input_language: Literal["ru", "kk", "mixed"]
    response_language: Literal["ru", "kk"]
    confidence: float = Field(ge=0, le=1)
    topic_relation: Literal["new", "continue", "restore", "complete", "none"]
    clarification_question: str | None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self):
        for name in ("scenarios", "alternatives"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {name}")
        if set(self.scenarios) & set(self.alternatives):
            raise ValueError("selected scenarios cannot be alternatives")
        if bool(self.scenarios) == bool(self.system_intent):
            raise ValueError("exactly one of business scenarios or system intent is required")
        if len(self.evidence) != len({e.evidence_id for e in self.evidence}):
            raise ValueError("duplicate evidence IDs")
        if self.scenarios and not self.evidence:
            raise ValueError("business routing requires attributable evidence")
        if self.system_intent == "SYS_UNCLEAR" and not self.clarification_question:
            raise ValueError("SYS_UNCLEAR requires a targeted question")
        return self


class Turn(StrictModel):
    turn_id: str
    role: Literal["user", "assistant"]
    text: str


class SourceRecord(StrictModel):
    source_id: str
    # Text is a serialized tool/KB record, not model-proposed data.
    content: str


class RouterInput(StrictModel):
    current_user_turn: Turn
    history: list[Turn] = Field(default_factory=list)
    active_scenario: str | None = None
    topic_stack: list[str] = Field(default_factory=list)
    current_slots: list[SlotUpdate] = Field(default_factory=list)
    known_evidence: list[EvidenceItem] = Field(default_factory=list)
    pending_action: str | None = None
    latest_backend_results: list[SourceRecord] = Field(default_factory=list)
    knowledge_records: list[SourceRecord] = Field(default_factory=list)
    response_language: Literal["ru", "kk"] | None = None

    @model_validator(mode="after")
    def unique_turns(self):
        if self.current_user_turn.role != "user":
            raise ValueError("current turn must be user")
        ids = [self.current_user_turn.turn_id, *[t.turn_id for t in self.history]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate turn IDs")
        return self
