from datetime import datetime, timezone
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


def now():
    return datetime.now(timezone.utc).isoformat()


def new_state(language='ru'):
    return dict(conversation_id=str(uuid4()), history=[], active_scenario=None, topic_stack=[],
                unresolved_topics=[], slots_by_topic={}, evidence=[], pending_questions=[], pending_action=None,
                latest_backend_results=[], language=language, response_language=language, turn_number=0,
                state_version=0, completed_actions={}, created_at=now(), updated_at=now())


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: str
    turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=8000)
    expected_state_version: int | None = None
    confirm_operation_id: str | None = None
    language: Literal['ru','kk'] | None = None
    input_mode: Literal['text','voice'] = 'text'
    stt_latency_ms: float | None = Field(default=None,ge=0)
