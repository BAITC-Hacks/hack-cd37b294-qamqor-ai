from __future__ import annotations

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException
from app.catalog.loader import checked_dataset, validate_dataset
from app.config.settings import Settings, ConfigurationError
from app.router.llm import LLMRouter
from app.router.schemas import RouterInput
from app.router.validator import ProposalError
from app.policy.engine import PolicyEngine
from app.policy.rules import reanalysis_reason


def create_app(settings: Settings | None = None, transport=None):
    settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app):
        dataset = checked_dataset(settings.dataset_path)
        app.state.dataset = dataset
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.router = LLMRouter(dataset, settings, client)
            app.state.policy = PolicyEngine(dataset)
            yield

    application = FastAPI(title="Halyk CallAI — routing core B0–B5", lifespan=lifespan)

    @application.get("/health")
    async def health():
        return {"status": "ok", "scope": "routing-core", "conversation_and_actions": "B6+ not implemented"}

    @application.get("/ready")
    async def ready():
        try:
            settings.require_api_key()
        except ConfigurationError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        return {"status": "configured", "model": settings.model, "api_access_verified": False,
                "dataset": validate_dataset(application.state.dataset)["counts"]}

    @application.post("/api/route")
    async def route(request: RouterInput):
        """Stateless core endpoint, shared with evaluation. No backend actions."""
        try:
            result = await application.state.router.route(request, reanalysis_reason)
        except ConfigurationError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        except ProposalError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        if result.proposal is None:
            raise HTTPException(502, detail={"kind": result.error_kind, "message": result.error,
                                             "attempts": len(result.attempts)})
        decision = application.state.policy.decide(result.proposal, request)
        return {"proposal": result.proposal.model_dump(), "decision": decision.model_dump(),
                "router_latency_ms": result.latency_ms, "retry_count": result.retry_count}

    return application


app = create_app()
