from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from collections.abc import Callable
import httpx
from pydantic import ValidationError
from app.catalog.loader import Dataset
from app.catalog.compiler import compile_catalog
from app.config.settings import Settings
from app.router.prompt import system_prompt
from app.router.schemas import RouterInput, RouterProposal
from app.router.validator import ProposalError, output_schema, validate_input, validate_proposal
from app.router.telemetry import usage_metrics, payload_hash, field_bytes


@dataclass
class RouterResult:
    proposal: RouterProposal | None
    attempts: list[dict] = field(default_factory=list)
    latency_ms: float = 0
    error: str | None = None
    error_kind: str | None = None

    @property
    def retry_count(self):
        return max(0, len(self.attempts) - 1)


def response_text(body: dict) -> str:
    if body.get("status") != "completed":
        raise ProposalError(f"Provider response not completed: {body.get('status')}")
    parts = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise ProposalError("Provider refused structured output")
            if content.get("type") == "output_text":
                parts.append(content["text"])
    if not parts:
        raise ProposalError("Provider returned no output text")
    return "".join(parts)


class LLMRouter:
    def __init__(self, dataset: Dataset, settings: Settings, client: httpx.AsyncClient):
        self.dataset = dataset
        self.settings = settings
        self.client = client
        self.catalog = compile_catalog(dataset)
        self.schema = output_schema(dataset)

    async def route(self, request: RouterInput,
                    reanalysis_trigger: Callable[[RouterProposal], str | None] | None = None) -> RouterResult:
        self.settings.require_api_key()
        validate_input(request, self.dataset)
        started = time.perf_counter()
        result = RouterResult(None)
        messages = [
            {"role": "system", "content": system_prompt(self.catalog)},
            {"role": "user", "content": json.dumps(request.model_dump(mode="json"), ensure_ascii=False)},
        ]
        for index in range(2):
            effort = "low" if index == 0 else "medium"
            payload = {"model": self.settings.model, "reasoning": {"effort": effort},
                       "input": messages, "store": False, "max_output_tokens": 6000,
                       "text": {"format": {"type": "json_schema", "name": "router_proposal", "strict": True, "schema": self.schema}}}
            attempt = {"number": index + 1, "retry_count": index, "effort": effort, "response_id": None,
                       "request_payload": deepcopy(payload), "request_sha256": payload_hash(payload),
                       "http_wall_ms": None, "schema_validation_ms": None, "response_json_bytes": None,
                       "policy_latency_ms": None}
            tick = time.perf_counter()
            result.attempts.append(attempt)
            raw_text = None
            http_tick = time.perf_counter()
            try:
                response = await self.client.post(
                    f"{self.settings.base_url}/responses", json=payload,
                    headers={"Authorization": f"Bearer {self.settings.api_key}"},
                    timeout=self.settings.timeout_seconds,
                )
                attempt["http_wall_ms"] = (time.perf_counter() - http_tick) * 1000
                attempt["response_json_bytes"] = len(response.content)
                attempt["http_status"] = response.status_code
                attempt["request_id"] = response.headers.get("x-request-id")
                if response.is_error:
                    # Never put request headers, API keys or arbitrary error bodies into logs.
                    result.error_kind = "API_ERROR"
                    result.error = f"OpenAI HTTP {response.status_code}"
                    break
                body = response.json()
                attempt.update(usage_metrics(body))
                attempt["response_id"] = body.get("id")
                attempt["raw_response"] = body
                raw_text = response_text(body)
                parsed = json.loads(raw_text)
                attempt["output_text_bytes"] = len(raw_text.encode())
                attempt["output_field_bytes"] = field_bytes(parsed)
                validation_tick = time.perf_counter()
                try:
                    proposal = validate_proposal(parsed, self.dataset, request)
                finally:
                    attempt["schema_validation_ms"] = (time.perf_counter() - validation_tick) * 1000
                attempt["normalized_boundary_pairs"] = [
                    {"before": [raw["scenario_id"], raw["neighbor_id"]],
                     "after": [check.scenario_id, check.neighbor_id], "source_rule": check.source_rule}
                    for raw, check in zip(parsed["boundary_checks"], proposal.boundary_checks)
                    if (raw["scenario_id"], raw["neighbor_id"]) != (check.scenario_id, check.neighbor_id)
                ]
                attempt["schema_valid"] = True
                trigger = reanalysis_trigger(proposal) if reanalysis_trigger else None
                if trigger and index == 0:
                    attempt["retry_reason"] = trigger
                    messages += [{"role": "assistant", "content": raw_text},
                                 {"role": "user", "content": "Reanalyse available evidence once. " + trigger + ". Do not invent missing facts."}]
                    continue
                result.proposal = proposal
                result.error = result.error_kind = None
                break
            except (ValidationError, ValueError, TypeError, KeyError) as exc:
                # This is schema/source recovery, not a substitute for unavailable evidence.
                error = str(exc)[:2000]
                attempt.update(schema_valid=False, validation_error=error)
                result.error_kind, result.error = "SCHEMA_ERROR", error
                if index == 0:
                    if raw_text:
                        messages.append({"role": "assistant", "content": raw_text})
                    messages.append({"role": "user", "content": "Repair schema/source validation once: " + error})
            except httpx.HTTPError as exc:
                attempt["http_wall_ms"] = (time.perf_counter() - http_tick) * 1000
                result.error_kind = "API_ERROR"
                result.error = type(exc).__name__
                break
            finally:
                attempt["latency_ms"] = (time.perf_counter() - tick) * 1000
        result.latency_ms = (time.perf_counter() - started) * 1000
        return result
