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
        assert all(f'SC{i:02}' in data["input"][0]["content"][0]["text"] for i in range(1, 41))
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


def test_per_request_telemetry_keeps_actual_payload_and_provider_usage(dataset):
    sent = []
    def handler(req):
        sent.append(json.loads(req.content))
        value = body({} if len(sent) == 1 else proposal())
        value["usage"] = {"input_tokens": 123, "input_tokens_details": {"cached_tokens": 100, "cache_write_tokens": 10},
                          "output_tokens": 40, "output_tokens_details": {"reasoning_tokens": 5}, "total_tokens": 163}
        return httpx.Response(200, json=value)
    result = invoke(dataset, handler)
    for index, attempt in enumerate(result.attempts):
        assert attempt["request_payload"] == sent[index]
        assert attempt["retry_count"] == index
        assert attempt["input_tokens"] == 123 and attempt["reasoning_tokens"] == 5
        assert attempt["http_wall_ms"] >= 0 and attempt["schema_validation_ms"] >= 0
        assert attempt["response_json_bytes"] > 0
        assert "Authorization" not in str(attempt)
    assert len(result.attempts[0]["request_payload"]["input"]) == 2
    assert len(result.attempts[1]["request_payload"]["input"]) == 4


def test_cache_prefix_is_invariant_and_user_state_is_last(dataset):
    async def run():
        sent = []
        def handler(req):
            sent.append(json.loads(req.content))
            return httpx.Response(200, json=body(proposal()))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            router = LLMRouter(dataset, Settings(api_key="test-not-real"), client)
            for text in ("оператор", "оператор пожалуйста"):
                await router.route(RouterInput(current_user_turn=Turn(turn_id="t1", role="user", text=text)))
        assert sent[0]["input"][0] == sent[1]["input"][0]
        assert sent[0]["text"] == sent[1]["text"]
        assert sent[0]["input"][1] != sent[1]["input"][1]
        assert list(json.loads(sent[0]["input"][1]["content"]))[-1] == "current_user_turn"
        assert sent[0]["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
        assert sent[0]["input"][0]["content"][0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    asyncio.run(run())


@pytest.mark.parametrize("generated", [False, True])
def test_prewarm_sends_no_user_and_rejects_generated_output(dataset, generated):
    async def run():
        def handler(req):
            data = json.loads(req.content)
            assert data["prompt_cache_options"]["prewarm"] is True
            assert len(data["input"]) == 1 and data["input"][0]["role"] == "system"
            return httpx.Response(200, json={"status": "completed", "output": [{}] if generated else [],
                                            "usage": {"output_tokens": int(generated)}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await LLMRouter(dataset, Settings(api_key="test-not-real"), client).prewarm()
        assert result["passed"] is (not generated)
    asyncio.run(run())
