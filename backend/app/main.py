from __future__ import annotations

from contextlib import asynccontextmanager
import time
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from dotenv import dotenv_values
import httpx
from fastapi import FastAPI, HTTPException
from app.catalog.loader import checked_dataset, validate_dataset
from app.config.settings import Settings, ConfigurationError
from app.router.llm import LLMRouter
from app.router.schemas import RouterInput
from app.router.validator import ProposalError
from app.policy.engine import PolicyEngine
from app.policy.rules import reanalysis_reason
from app.state.repository import Repository
from app.state.service import ConversationService
from app.state.models import ChatRequest
from app.slots.manager import SlotManager
from app.actions.mock_backend import MockBackend
from app.actions.dispatcher import Dispatcher
from app.kb.service import KnowledgeBase
from app.response.composer import Composer
from app.observability.tracer import Tracer
from app.voice.providers import OpenAIAudio
from app.voice.routes import voice_routes


class SessionRequest(BaseModel):
    language: Literal['ru','kk'] = 'ru'


def create_app(settings: Settings | None = None, transport=None, database_path=None):
    explicit_settings = settings is not None
    settings = settings or Settings.load()
    if not explicit_settings and settings.model != 'gpt-6-astra':
        raise ConfigurationError('Golden L2 requires CALLAI_MODEL=gpt-6-astra. Restore the locked configuration.')

    @asynccontextmanager
    async def lifespan(app):
        dataset = checked_dataset(settings.dataset_path)
        app.state.dataset = dataset
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.audio = OpenAIAudio(settings, client)
            app.state.router = LLMRouter(dataset, settings, client)
            app.state.policy = PolicyEngine(dataset)
            project_root = Path(__file__).parents[2]
            repository = Repository(database_path or os.getenv('CALLAI_DATABASE') or dotenv_values(project_root/'.env').get('CALLAI_DATABASE') or project_root/'runtime'/'callai.sqlite', dataset.documents['mock_backend.json'])
            kb = KnowledgeBase(dataset)
            slots = SlotManager(dataset)
            tracer = Tracer(repository)
            tracer.start()
            app.state.repository, app.state.tracer = repository, tracer
            app.state.conversations = ConversationService(repository, app.state.router, app.state.policy, slots,
                Dispatcher(dataset, MockBackend(dataset, repository, kb), slots, kb), Composer(settings, client), tracer)
            try:
                yield
            finally:
                await tracer.close()

    application = FastAPI(title="Halyk CallAI", lifespan=lifespan)
    application.include_router(voice_routes())

    @application.get("/health")
    async def health():
        return {"status": "ok", "scope": "conversation", "routing": "golden-L2", "backend": "mock"}

    @application.post('/api/session')
    async def create_session(body: SessionRequest):
        return application.state.conversations.create(body.language)

    @application.get('/api/session/{conversation_id}')
    async def session(conversation_id: str):
        return application.state.conversations.get(conversation_id)

    @application.post('/api/chat')
    async def chat(body: ChatRequest):
        try:
            return await application.state.conversations.chat(body)
        except ConfigurationError as exc:
            raise HTTPException(503, str(exc)) from exc
        except ProposalError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.get('/api/supervisor/sessions')
    async def sessions():
        return application.state.repository.sessions()

    @application.get('/api/supervisor/session/{conversation_id}')
    async def supervisor_session(conversation_id: str):
        return {'state': application.state.conversations.get(conversation_id),
                'events': application.state.tracer.events(conversation_id)}

    @application.get('/api/supervisor/events')
    async def events(conversation_id: str | None = None):
        return {'events': application.state.tracer.events(conversation_id), 'dropped': application.state.tracer.dropped}

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
        tick = time.perf_counter()
        decision = application.state.policy.decide(result.proposal, request)
        policy_ms = (time.perf_counter() - tick) * 1000
        result.attempts[-1]["policy_latency_ms"] = policy_ms
        return {"proposal": result.proposal.model_dump(), "decision": decision.model_dump(),
                "router_latency_ms": result.latency_ms, "retry_count": result.retry_count,
                "policy_latency_ms": policy_ms,
                "request_metrics": [{k: v for k, v in a.items() if k not in {"request_payload", "raw_response"}}
                                    for a in result.attempts]}

    return application


app = create_app()
