import asyncio
import json
import httpx
from app.config.settings import Settings
from app.main import create_app


def test_health_works_and_readiness_reports_missing_key():
    async def run():
        app = create_app(Settings(api_key=""))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/ready")).status_code == 503
                result = await client.post("/api/route", json={"current_user_turn": {"turn_id": "t1", "role": "user", "text": "Сәлем"}})
                assert result.status_code == 503
                assert "OPENAI_API_KEY" in result.json()["detail"]
    asyncio.run(run())


def test_invalid_request_is_not_routed():
    async def run():
        app = create_app(Settings(api_key=""))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                assert (await client.post("/api/route", json={"text": "hello"})).status_code == 422
    asyncio.run(run())


def test_http_route_uses_validated_proposal_and_policy():
    # Transport fixture only; never an official evaluation prediction.
    output = dict(scenarios=["SC37"], alternatives=[], system_intent=None,
                  evidence=[dict(evidence_id="e1", fact="wants human", source_type="user_turn", source_id="t1",
                                 quote="Оператор", polarity="positive", supersedes=None)],
                  boundary_checks=[], slot_updates=[], input_language="ru", response_language="ru", confidence=0.9,
                  topic_relation="new", clarification_question=None, reason="Explicit operator request")
    def handler(req):
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(output)}]}]})
    async def run():
        app = create_app(Settings(api_key="fixture-key"), httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                result = await client.post("/api/route", json={"current_user_turn": {"turn_id": "t1", "role": "user", "text": "Оператор"}})
                assert result.status_code == 200
                assert result.json()["decision"]["action"] == "HANDOFF"
                assert result.json()["decision"]["handoff_queue"] == "operator_general"
                assert result.json()["decision"]["execution_allowed"] is False
                assert "fixture-key" not in result.text
    asyncio.run(run())
