"""Thin wrapper over the Anthropic SDK for schema-constrained calls.

Every call returns (validated pydantic object, meta). The meta (model that
actually served it, token usage, stop reason, whether a fallback ran) goes
into the step's trace record.
"""
from typing import Any, Dict, Optional, Tuple, Type, TypeVar

import copy

import anthropic
import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, settings: Settings, client: Optional[anthropic.Anthropic] = None,
                 model: Optional[str] = None):
        self.model = model or settings.model
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    def structured(self, *, system: str, user: str, output_model: Type[T],
                   effort: str = "medium", max_tokens: int = 16000) -> Tuple[T, Dict[str, Any]]:
        schema = output_model.model_json_schema()
        kwargs: Dict[str, Any] = {}
        if self.model.startswith("claude-opus"):
            # server-side fallback on a policy decline; offered for Opus, not for Haiku
            kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                **kwargs,
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic authentication failed - check ANTHROPIC_API_KEY") from e
        except anthropic.BadRequestError as e:
            raise LLMError(f"Anthropic rejected the request: {e.message}") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic rate limit hit - retry later") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API") from e

        meta = {
            "model": resp.model,
            "stop_reason": resp.stop_reason,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "fallback_ran": any(getattr(i, "type", "") == "fallback_message"
                                for i in (getattr(resp.usage, "iterations", None) or [])),
        }
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            raise LLMError(f"Model declined the request ({getattr(details, 'category', None)})")
        if resp.stop_reason == "max_tokens":
            raise LLMError("Model output hit max_tokens before finishing")

        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise LLMError("No text block in model response")
        try:
            return output_model.model_validate_json(text), meta
        except ValidationError as e:
            raise LLMError(f"Model output failed schema validation: {e}") from e


# ---------------- Gemini (Google AI Studio key) ----------------

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_BAD_FINISH = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE", "OTHER"}


def gemini_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Pydantic JSON Schema -> a plain schema Gemini accepts: $refs inlined, titles dropped,
    Optional[X] (anyOf X|null) written as type [X, "null"]."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node):
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
        node = {k: v for k, v in node.items() if k not in ("title", "default")}
        if "anyOf" in node:
            opts = node["anyOf"]
            non_null = [o for o in opts if o.get("type") != "null"]
            if len(non_null) == 1 and len(opts) == 2 and "type" in non_null[0]:
                merged = walk(non_null[0])
                merged["type"] = [merged["type"], "null"]
                rest = {k: v for k, v in node.items() if k != "anyOf"}
                return {**rest, **merged}
        return {k: walk(v) for k, v in node.items()}

    return walk(raw)


class GeminiLLM:
    """Same interface as LLM.structured, backed by the Gemini API."""

    def __init__(self, api_key: str, model: str, http: Optional[httpx.Client] = None):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.model = model
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=180.0)

    def structured(self, *, system: str, user: str, output_model: Type[T],
                   effort: str = "medium", max_tokens: int = 16000) -> Tuple[T, Dict[str, Any]]:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": gemini_schema(output_model),
                "maxOutputTokens": max_tokens,
            },
        }
        try:
            r = self.http.post(GEMINI_URL.format(model=self.model), json=body,
                               headers={"x-goog-api-key": self.api_key})
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach the Gemini API: {type(e).__name__}") from e
        if r.status_code in (401, 403):
            raise LLMError("Gemini authentication failed - check GEMINI_API_KEY")
        if r.status_code == 429:
            raise LLMError("Gemini rate limit or quota hit - retry later")
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text[:300])
            except ValueError:
                msg = r.text[:300]
            raise LLMError(f"Gemini API error {r.status_code}: {msg}")

        data = r.json()
        usage = data.get("usageMetadata", {})
        cand = (data.get("candidates") or [{}])[0]
        finish = cand.get("finishReason")
        meta = {
            "model": data.get("modelVersion") or self.model,
            "stop_reason": finish,
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "thinking_tokens": usage.get("thoughtsTokenCount"),
            "fallback_ran": False,
        }
        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise LLMError(f"Gemini blocked the prompt ({block})")
        if finish in GEMINI_BAD_FINISH:
            raise LLMError(f"Gemini stopped without an answer ({finish})")
        if finish == "MAX_TOKENS":
            raise LLMError("Gemini output hit maxOutputTokens before finishing")
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            raise LLMError("No text in Gemini response")
        try:
            return output_model.model_validate_json(text), meta
        except ValidationError as e:
            raise LLMError(f"Gemini output failed schema validation: {e}") from e


def make_llm(settings, role: str, client=None):
    """role = 'extract' (cheap model) or 'qualify' (stronger model)."""
    if settings.provider == "gemini":
        model = settings.gemini_extract_model if role == "extract" else settings.gemini_model
        return GeminiLLM(settings.gemini_api_key, model)
    model = settings.extract_model if role == "extract" else settings.model
    return LLM(settings, client=client, model=model)
