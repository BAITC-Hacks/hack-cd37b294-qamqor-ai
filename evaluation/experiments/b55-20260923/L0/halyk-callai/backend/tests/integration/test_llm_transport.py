import asyncio
import json
import httpx
import pytest
from app.config.settings import Settings, ConfigurationError
from app.router.llm import LLMRouter
from app.router.schemas import RouterInput, Turn


def proposal():
    return dict(scenarios=["SC37"], alternatives=[], system_intent=None,
                evidence=[dict(evidence_id="t1:e1", fact="Wants operator", source_type="user_turn", source_id="t1",
                               quote="оператор", polarity="positive", supersedes=None)],
                boundary_checks=[], slot_updates=[], input_language="ru", response_language="ru", confidence=0.9,
                topic_relation="new", clarification_question=None, reason="Explicit human request")


def body(value):
    return {"id": "test_response", "status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(value, ensure_ascii=False)}]}]}


def invoke(dataset, handler, trigger=None, key="test-not-real"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            router = LLMRouter(dataset, Settings(api_key=key), client)
            return await router.route(RouterInput(current_user_turn=Turn(turn_id="t1", role="user", text="оператор")), trigger)
    return asyncio.run(run())


def test_request_contract_full_catalog_low_effort(dataset):
    def handler(req):
        data = json.loads(req.content)
        assert data["model"] == "gpt-6-astra"
        assert data["reasoning"]["effort"] == "low"
        assert data["text"]["format"]["strict"] is True
        assert all(f'SC{i:02}' in data["input"][0]["content"] for i in range(1, 41))
        assert "U001" not in req.content.decode()
        return httpx.Response(200, json=body(proposal()))
    result = invoke(dataset, handler)
    assert result.proposal.scenarios == ["SC37"]
    assert result.retry_count == 0


def test_schema_recovery_once_at_medium(dataset):
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json=body({} if len(calls) == 1 else proposal()))
    result = invoke(dataset, handler)
    assert result.proposal is not None
    assert [c["reasoning"]["effort"] for c in calls] == ["low", "medium"]


def test_schema_and_semantic_retries_share_budget(dataset):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=body({} if len(calls) == 1 else proposal()))
    result = invoke(dataset, handler, lambda _: "Evidence conflicts")
    assert len(calls) == 2
    assert result.proposal is not None


def test_exhaustion_does_not_fabricate_scenario(dataset):
    result = invoke(dataset, lambda _: httpx.Response(200, json=body({})))
    assert len(result.attempts) == 2
    assert result.proposal is None and result.error_kind == "SCHEMA_ERROR"


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_api_failure_is_not_a_system_intent(dataset, status):
    result = invoke(dataset, lambda _: httpx.Response(status, json={"error": "private"}))
    assert result.error == f"OpenAI HTTP {status}"
    assert result.error_kind == "API_ERROR" and result.proposal is None
    assert len(result.attempts) == 1


def test_no_key_is_configuration_error(dataset):
    with pytest.raises(ConfigurationError):
        invoke(dataset, lambda _: pytest.fail("must not call API"), key="")


def test_low_confidence_alone_does_not_retry(dataset):
    output = proposal()
    output["confidence"] = 0.1
    result = invoke(dataset, lambda _: httpx.Response(200, json=body(output)))
    assert len(result.attempts) == 1
