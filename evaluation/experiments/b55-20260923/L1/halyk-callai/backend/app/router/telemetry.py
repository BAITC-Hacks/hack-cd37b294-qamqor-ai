"""Observed request usage only: missing provider fields remain null, never zero."""
import hashlib
import json


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def usage_metrics(body):
    usage = body.get("usage") or {}
    inputs = usage.get("input_tokens_details") or {}
    outputs = usage.get("output_tokens_details") or {}
    return {"input_tokens": usage.get("input_tokens"), "cached_tokens": inputs.get("cached_tokens"),
            "cache_write_tokens": inputs.get("cache_write_tokens"), "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": outputs.get("reasoning_tokens"), "total_tokens": usage.get("total_tokens")}


def field_bytes(payload):
    """Exact UTF-8 field value sizes, not guessed token counts."""
    if not isinstance(payload, dict):
        return {}
    return {key: len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
            for key, value in payload.items()}
